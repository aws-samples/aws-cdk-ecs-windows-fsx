from aws_cdk import (
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_autoscaling as autoscaling,
    aws_iam as iam,
    aws_elasticloadbalancingv2 as elbv2,
    aws_ecs_patterns as ecs_patterns,
    aws_ecr as ecr,
    aws_logs as logs,
    aws_route53 as r53,
    core
)

class CdkEcsWindowsFSXBastion(core.Stack):

    def __init__(self, scope: core.Construct, id: str, vpc: ec2.Vpc, bastion_sg: ec2.SecurityGroup, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        role = iam.Role(self, 'ec2-bastion-role',
            assumed_by=iam.ServicePrincipal('ec2.amazonaws.com')
        )
        
        # Grant permission to access the MAD secret
        role.add_managed_policy(policy=iam.ManagedPolicy.from_managed_policy_arn(self, 'MP1', 'arn:aws:iam::aws:policy/SecretsManagerReadWrite'))
        role.add_managed_policy(policy=iam.ManagedPolicy.from_managed_policy_arn(self, 'MP2', 'arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore'))

        # Setup UserData
        user_data= '<powershell> \n'
        user_data+= 'Import-Module AWSPowerShell \n'
        user_data+= 'New-NetFirewallRule -DisplayName "Allow local VPC" -Direction Inbound -LocalAddress 10.0.0.0/8 -LocalPort Any -Action Allow \n'
        user_data+= 'ADD-WindowsFeature RSAT-AD-Tools \n'
        user_data+= 'ADD-WindowsFeature RSAT-DNS-Server \n'
        user_data+= '[string]$SecretAD  = "MADSecret" \n'
        user_data+= '$SecretObj = Get-SECSecretValue -SecretId $SecretAD \n'
        user_data+= '[PSCustomObject]$Secret = ($SecretObj.SecretString  | ConvertFrom-Json) \n'
        user_data+= '$password   = $Secret.Password | ConvertTo-SecureString -asPlainText -Force \n'
        user_data+= '$username   = $Secret.username + "@" + $Secret.Domain \n'
        user_data+= '$credential = New-Object System.Management.Automation.PSCredential($username,$password) \n'
        user_data+= 'Add-Computer -DomainName $Secret.Domain -Credential $credential -Restart -Force \n'
        user_data+= '</powershell> \n'

        # Create Bastion
        bastion = ec2.Instance(self, 'Bastion',
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.BURSTABLE3, ec2.InstanceSize.MEDIUM),
            machine_image=ec2.MachineImage.from_ssm_parameter(
                parameter_name='/aws/service/ami-windows-latest/Windows_Server-2019-English-Full-Base',
                os=ec2.OperatingSystemType.WINDOWS
            ),
            vpc=vpc,
            user_data=ec2.UserData.custom(user_data),
            #key_name='ec2_key',
            role=role,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=bastion_sg
        )

        core.CfnOutput(self, "Bastion Host",
            value=bastion.instance_public_dns_name
        )
        