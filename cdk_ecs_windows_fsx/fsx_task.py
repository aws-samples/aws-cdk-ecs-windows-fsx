from aws_cdk import (
    aws_iam as iam,
    custom_resources,
)

def custom_fsx_task(self, host_port: int, family: str, file_system_id: str, mad_secret_arn: str, mad_domain_name: str, task_role: iam.Role, execution_role: iam.Role): 
    on_create_aws_sdk_call=custom_resources.AwsSdkCall(
        physical_resource_id=custom_resources.PhysicalResourceId.from_response('taskDefinition.taskDefinitionArn'),
        service="ECS",
        action="registerTaskDefinition", # https://docs.aws.amazon.com/AWSJavaScriptSDK/latest/AWS/ECS.html (watch out for camel case!)
        parameters={
            "family": family,
            "taskRoleArn": task_role.role_arn,
            "executionRoleArn": execution_role.role_arn,
            "containerDefinitions": [
                {
                    "name": "IISContainer",
                    "image": "microsoft/iis",
                    "cpu": 512,
                    "memory": 1024,
                    "links": [],
                    "portMappings": [
                        {
                            "containerPort": 80,
                            "hostPort": host_port,
                            "protocol": "tcp"
                        }
                    ],
                    "essential": True,
                    "entryPoint": [
                        "powershell",
                        "-Command"
                    ],
                    "mountPoints": [
                        {
                            "sourceVolume": file_system_id,
                            "containerPath": 'C:\\fsx-windows-dir',
                            "readOnly": False
                        },
                    ],
                    "command": [
                        '$IndexFilePath = "C:\\fsx-windows-dir\\index.html"; if ((Test-Path -Path $IndexFilePath) -ne $true){New-Item -Path $IndexFilePath -ItemType file -Value "<html> <head> <title>Amazon ECS Sample App</title> <style>body {margin-top: 40px; background-color: #ff3;} </style> </head><body> <div style=color:black;text-align:center> <h1>Amazon ECS Sample App</h1> <h2>Congratulations!</h2> <p>Your application is now running on a container in Amazon ECS.</p> <table style=margin-left:auto;margin-right:auto;><tr><th>TimeStamp</th><th>Task ID</th></tr>" -Force;}; $datetime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"; $TaskId = (Invoke-RestMethod -Method GET -Uri $env:ECS_CONTAINER_METADATA_URI_V4/task).TaskARN.split("/")[2]; Add-Content -Path $IndexFilePath -Value "<tr><th>$datetime</th><th>$TaskId</th></tr>"; Copy-Item -Path $IndexFilePath -Destination C:\\inetpub\\wwwroot\\index.html -Force; C:\\ServiceMonitor.exe w3svc;'
                    ]
                }
            ],
            "volumes": [
                {
                    'name': file_system_id,
                    'fsxWindowsFileServerVolumeConfiguration': {
                        'fileSystemId': file_system_id,
                        'rootDirectory': 'share',
                        'authorizationConfig': {
                            'credentialsParameter': mad_secret_arn,
                            'domain': mad_domain_name
                        }
                    }
                },
            ],
            "requiresCompatibilities": [
                'EC2'
            ]
        }
    )

    on_delete_aws_sdk_call=custom_resources.AwsSdkCall(
        physical_resource_id=custom_resources.PhysicalResourceId.from_response('taskDefinition.taskDefinitionArn'),
        service="ECS",
        action="deregisterTaskDefinition", # https://docs.aws.amazon.com/AWSJavaScriptSDK/latest/AWS/ECS.html (watch out for camel case!)
        parameters={
            "taskDefinition": custom_resources.PhysicalResourceIdReference() # https://docs.aws.amazon.com/cdk/api/latest/docs/custom-resources-readme.html#physical-resource-id-parameter 
        }
    )

    custom_task = custom_resources.AwsCustomResource(self, "FSXTaskResource",
        policy=custom_resources.AwsCustomResourcePolicy.from_statements(
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "ecs:*"
                    ],
                    resources=["*"]
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "iam:PassRole"
                    ],
                    resources=[
                        task_role.role_arn,
                        execution_role.role_arn
                    ]
                )
            ]
        ),
        on_create=on_create_aws_sdk_call,
        on_update=on_create_aws_sdk_call,
        on_delete=on_delete_aws_sdk_call
    )

    task_definition_arn = custom_task.get_response_field('taskDefinition.taskDefinitionArn')
    return task_definition_arn