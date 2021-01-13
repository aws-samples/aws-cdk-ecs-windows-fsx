#!/usr/bin/env python3

import boto3
from aws_cdk import core

from cdk_ecs_windows_fsx.cdk_ecs_windows_fsx_cluster import CdkEcsWindowsFSXCluster
from cdk_ecs_windows_fsx.cdk_ecs_windows_fsx_bastion import CdkEcsWindowsFSXBastion
from cdk_ecs_windows_fsx.cdk_ecs_windows_fsx_website import CdkEcsWindowsFSXWebsite

# Params
env = core.Environment(
    account=boto3.client('sts').get_caller_identity().get('Account'),
    region="eu-west-1"
)

app = core.App()
hosted_zone_id = app.node.try_get_context('hosted_zone_id')
if hosted_zone_id is None:
    hosted_zone_id = ''

zone_name = app.node.try_get_context('zone_name')
if zone_name is None:
    zone_name = ''

cluster = CdkEcsWindowsFSXCluster(app, "cdk-ecs-windows-cluster", 
    env=env
)
CdkEcsWindowsFSXBastion(app, "cdk-ecs-windows-bastion", 
    vpc=cluster.vpc, 
    bastion_sg=cluster.bastion_sg, 
    env=env
)
CdkEcsWindowsFSXWebsite(app, "cdk-ecs-windows-website1", 
    cluster=cluster.cluster, 
    env=env, 
    hosted_zone_id=hosted_zone_id, 
    zone_name=zone_name, 
    sub_domain="website1", 
    host_port=8081, # This port must be unique per task/cluster i.e. increment it per site
    file_system_id = cluster.file_system_id, 
    mad_secret_arn = cluster.mad_secret_arn, 
    mad_domain_name = cluster.mad_domain_name
)

app.synth()
