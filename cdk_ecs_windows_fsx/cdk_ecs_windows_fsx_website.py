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
    custom_resources,
    core
)
from fsx_task import custom_fsx_task

class CdkEcsWindowsFSXWebsite(core.Stack):

    def __init__(self, scope: core.Construct, id: str, cluster: ecs.Cluster, hosted_zone_id: str, zone_name: str, sub_domain: str, host_port: int, file_system_id: str, mad_secret_arn: str, mad_domain_name: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # check context values
        for v in [sub_domain, hosted_zone_id, zone_name]:
            if v == '':
                raise Exception("Please provide required parameters sub_domain, hosted_zone_id, zone_name via context variables") 

        # configure zone
        domain_zone = r53.PublicHostedZone.from_hosted_zone_attributes(self, "hosted_zone",
            hosted_zone_id=hosted_zone_id,
            zone_name=zone_name
        )
        domain_name = sub_domain + "." + zone_name

        # setup for pseudo parameters
        stack = core.Stack.of(self)

        ## Custom Resource - Task
        family = stack.stack_name + "_webserver"

        task_role = iam.Role(self, "TaskRole",
            role_name=family + '_task',
            assumed_by=iam.ServicePrincipal('ecs-tasks.amazonaws.com')
        )

        execution_role = iam.Role(self, "ExecutionRole",
            role_name=family + '_execution',
            assumed_by=iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
            inline_policies=[
                iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[            
                                "secretsmanager:GetSecretValue",
                                "secretsmanager:DescribeSecret"
                            ],
                            resources=[
                                mad_secret_arn
                            ]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[            
                                "fsx:DescribeFileSystems"
                            ],
                            resources=[
                                "*"
                            ]
                        )
                    ]
                )
            ],
            managed_policies=[
                iam.ManagedPolicy.from_managed_policy_arn(self,"AmazonECSTaskExecutionRolePolicy",'arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy')
            ]
        )

        # Custom Task Definition
        task_definition_arn = custom_fsx_task(self, 
            host_port=host_port,
            family=family, 
            file_system_id=file_system_id, 
            mad_secret_arn=mad_secret_arn,
            mad_domain_name=mad_domain_name,
            task_role=task_role, 
            execution_role=execution_role
        )
        
        # importing a task is broken https://github.com/aws/aws-cdk/issues/6240
        # task_definition = ecs.Ec2TaskDefinition.from_ec2_task_definition_arn(self, "TaskDef", ec2_task_definition_arn=task_definition_arn)
        
        # Task Definition - Work Around Part 1 (Create a temp task, this won't actually be used)
        task_definition = ecs.Ec2TaskDefinition(self, "TaskDef",
            #network_mode=ecs.NetworkMode.DEFAULT # Parameter not available yet, escape hatch required
        )

        # Edit Ec2TaskDefinition via an Escape Hatch to remove network_mode (required for windows) - This Task Definition is completely ignored for now...
        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-ecs-taskdefinition.html#cfn-ecs-taskdefinition-networkmode
        cfn_task_definition = task_definition.node.default_child
        cfn_task_definition.add_property_deletion_override('NetworkMode')

        container = task_definition.add_container("IISContainer",
            image=ecs.ContainerImage.from_registry('microsoft/iis'),
            memory_limit_mib=1028,
            cpu=512,
            entry_point=["powershell", "-Command"],
            command=["C:\\ServiceMonitor.exe w3svc"],
        )

        container.add_port_mappings(ecs.PortMapping(
            protocol=ecs.Protocol.TCP,
            container_port=80,
            host_port=host_port
        ))
        # Task Definition - Work Around Part 1 End

        # ECS Service, ALB, Cert
        ApplicationLoadBalancedEc2Service = ecs_patterns.ApplicationLoadBalancedEc2Service(self, "iis-service",
            cluster=cluster,
            task_definition=task_definition,
            desired_count=2,
            domain_name=domain_name,
            domain_zone=domain_zone,
            protocol=elbv2.ApplicationProtocol.HTTPS,
            redirect_http=True
        )

        # Task Definition - Work Around Part 2 (Override the temp task we created earlier that won't actually be used)
        cfn_service = ApplicationLoadBalancedEc2Service.node.find_child('Service').node.find_child('Service')
        cfn_service.add_property_override('TaskDefinition', task_definition_arn)
        # Task Definition - Work Around Part 2 End
