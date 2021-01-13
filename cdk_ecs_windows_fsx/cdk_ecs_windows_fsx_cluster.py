from aws_cdk import (
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_autoscaling as autoscaling,
    aws_iam as iam,
    aws_elasticloadbalancingv2 as elbv2,
    aws_ecs_patterns as ecs_patterns,
    aws_ecr as ecr,
    aws_logs as logs,
    aws_secretsmanager as secretsmanager,
    aws_directoryservice as mad,
    aws_fsx as fsx,
    core
)
import simplejson as json


class CdkEcsWindowsFSXCluster(core.Stack):

    def __init__(self, scope: core.Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # setup for pseudo parameters
        stack = core.Stack.of(self)

        # New VPC
        vpc = ec2.Vpc(self, "Vpc",
            max_azs=2,
            nat_gateways=2,
            subnet_configuration=[
                {
                    'name': 'public',
                    'subnetType': ec2.SubnetType.PUBLIC,
                    'cidrMask': 24,
                    'reserved': False,
                },
                {
                    'name': 'private',
                    'subnetType': ec2.SubnetType.PRIVATE,
                    'cidrMask': 24,
                    'reserved': False,
                },
                {
                    'name': 'isolated',
                    'subnetType': ec2.SubnetType.ISOLATED,
                    'cidrMask': 24,
                    'reserved': True,
                }
            ]
        )

        ## Secrets Manager - Generate Managed Active Directory Admin Credentials
        domain_name='example.aws' ## Managed AD domain name
        mad_password_object = {'Domain': domain_name, 'username': 'Admin'}
        self.MADSecret = secretsmanager.Secret(self,"MADSecret",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template=json.dumps(mad_password_object),
                generate_string_key='Password',
                exclude_punctuation=True,
            ),
            secret_name="MADSecret"
        )

        ## ECS 
        cluster = ecs.Cluster(self, "cluster",
            vpc=vpc,
            capacity=ecs.AddCapacityOptions(
                instance_type=ec2.InstanceType.of(ec2.InstanceClass.BURSTABLE3, ec2.InstanceSize.MEDIUM),
                machine_image=ec2.MachineImage.from_ssm_parameter(
                    parameter_name='/aws/service/ami-windows-latest/Windows_Server-2019-English-Core-ECS_Optimized/image_id',
                    os=ec2.OperatingSystemType.WINDOWS
                ),
                min_capacity=2,
                max_capacity=2
            )
        )

        # Edit Launch Config for the ECS Cluster Hosts via an Escape Hatch to insert correct Windows UserData
        launchConfig = cluster.node.find_child('DefaultAutoScalingGroup').node.find_child('LaunchConfig')
        userDataScript = '<powershell> \n'
        userDataScript += 'Import-Module ECSTools \n' 
        userDataScript += 'Initialize-ECSAgent -Cluster ' + cluster.cluster_name + ' -EnableTaskIAMRole \n' 
        userDataScript += '[string]$SecretAD  = "' + self.MADSecret.secret_name + '" \n'
        userDataScript += '$SecretObj = Get-SECSecretValue -SecretId $SecretAD \n'
        userDataScript += '[PSCustomObject]$Secret = ($SecretObj.SecretString  | ConvertFrom-Json) \n'
        userDataScript += '$password   = $Secret.Password | ConvertTo-SecureString -asPlainText -Force \n'
        userDataScript += '$username   = $Secret.username + "@" + $Secret.Domain \n'
        userDataScript += '$credential = New-Object System.Management.Automation.PSCredential($username,$password) \n'
        userDataScript += 'Add-Computer -DomainName $Secret.Domain -Credential $credential -Restart -Force \n'
        userDataScript += '</powershell> \n'
        userDataScript += '<persist>true</persist>'

        launchConfig.add_property_override('UserData', core.Fn.base64(userDataScript))

        # Export Cluster for consumption in website stacks
        self.cluster = cluster

        ## Managed Active Directory        
        # Grant ECS Cluster Instances permission to Secrets Manager MADSecret - metadata path cdk-ecs-windows-cluster/cluster/DefaultAutoScalingGroup/InstanceRole/Resource
        ecs_instance_role = cluster.node.find_child('DefaultAutoScalingGroup').node.find_child('InstanceRole')
        # Grant permission to access the MAD secret
        ecs_instance_role.add_managed_policy(policy=iam.ManagedPolicy.from_managed_policy_arn(self, 'MP1', 'arn:aws:iam::aws:policy/SecretsManagerReadWrite'))
        # Grant permissions to enable Systems Manager to manage ECS Hosts
        ecs_instance_role.add_managed_policy(policy=iam.ManagedPolicy.from_managed_policy_arn(self, 'MP2', 'arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore'))
        
        # Find Private subnets of the VPC
        private_subnets = vpc.select_subnets(subnet_type= ec2.SubnetType.PRIVATE).subnet_ids
        
        # Set Managed Active Directory VPC and Subnet config
        vpcSettings = mad.CfnMicrosoftAD.VpcSettingsProperty(subnet_ids=private_subnets,vpc_id=vpc.vpc_id)
        
        # Launch Managed Active Directory
        ad = mad.CfnMicrosoftAD(self,'MAD',
            name=domain_name,
            password=self.MADSecret.secret_value_from_json('Password').to_string(),
            vpc_settings=vpcSettings,
            edition='Standard'
        )

        # Collect the IPs of the two created Domain Controllers
        ad_dns_ip1 = core.Fn.select(0,ad.attr_dns_ip_addresses)
        ad_dns_ip2 = core.Fn.select(1,ad.attr_dns_ip_addresses)

        ## FSx
        # Create a Security Group for FSx
        fsx_sg = ec2.SecurityGroup(self, 'WindowsFSxSG',
            vpc=vpc,
            allow_all_outbound=True
        )
        core.Tags.of(fsx_sg).add('Name',stack.stack_name + '_FSx')

        # Allow ECS Cluster to Connect to FSx Hosts
        fsx_sg.connections.allow_from(cluster.connections, ec2.Port.tcp(445), 'ECS Cluster')
        fsx_sg.connections.allow_from(cluster.connections, ec2.Port.tcp(5985), 'ECS Cluster')

        # Create FSx
        FSxSize = 32 # GB (32 GB min)
        FSxMBps = 8 # MB/s (8 MB/s min)
        windows_fsx = fsx.CfnFileSystem(self, 'WindowsFSx', file_system_type='WINDOWS',subnet_ids=private_subnets,
            windows_configuration=fsx.CfnFileSystem.WindowsConfigurationProperty(
                active_directory_id=ad.ref,
                throughput_capacity=FSxMBps,
                preferred_subnet_id=private_subnets[0],
                deployment_type="MULTI_AZ_1"
            ),
            storage_capacity=FSxSize,
            security_group_ids=[fsx_sg.security_group_id]
        )

        ## DHCP Options - Configure VPC DNS to use MAD
        dhcp_options = ec2.CfnDHCPOptions(self, 'DHCPOptions',
            domain_name=ad.name,
            domain_name_servers=[ad_dns_ip1,ad_dns_ip2],
            ntp_servers=["169.254.169.123"]
        )

        ec2.CfnVPCDHCPOptionsAssociation(self, 'DHCPOptionsAssoc',
            vpc_id=vpc.vpc_id, 
            dhcp_options_id=dhcp_options.ref
        )

        ## Bastion Security Group - Created here to avoid a circular dependency
        self.bastion_sg = ec2.SecurityGroup(self, 'BastionSG',
            vpc=vpc,
            allow_all_outbound=True
        )
        core.Tags.of(self.bastion_sg).add('Name',stack.stack_name + '_Bastion')

        # Allow access to FSx/Cluster from Bastion Server # https://docs.aws.amazon.com/FSx/latest/WindowsGuide/limit-access-security-groups.html
        fsx_sg.add_ingress_rule(self.bastion_sg, ec2.Port.tcp(445), 'Bastion')
        fsx_sg.add_ingress_rule(self.bastion_sg, ec2.Port.tcp(5985), 'Bastion')
        cluster.connections.allow_from(self.bastion_sg, ec2.Port.tcp(3389), 'Bastion')

        # Allow access to Bastion from your home/office IP range (Update with your home/office IP)
        #self.bastion_sg.add_ingress_rule(ec2.Peer.ipv4('0.0.0.0/0'), ec2.Port.tcp(3389), 'Access from Internet RDP')

        # Export Values to be consumed by other stacks
        self.vpc = vpc
        self.file_system_id = windows_fsx.ref
        self.mad_secret_arn = self.MADSecret.secret_arn
        self.mad_domain_name = domain_name
