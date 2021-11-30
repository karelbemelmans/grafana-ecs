from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_ecs_patterns as ecs_patterns
# For consistency with other languages, `cdk` is the preferred import name for
# the CDK's core module.  The following line also imports it as `core` for use
# with examples from the CDK Developer's Guide, which are in the process of
# being updated to use `cdk`.  You may delete this import if you don't need it.
from aws_cdk import core
from aws_cdk import core as cdk


class GrafanaEcsStack(cdk.Stack):

    def __init__(self, scope: cdk.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create a VPC with all the defaults CDK uses
        vpc = ec2.Vpc(self, "GrafanaVPC", max_azs=3)

        # Create an ECS cluster with all the defaults from CDK
        cluster = ecs.Cluster(self, "GrafanaCluster", vpc=vpc)

        # Task definition
        task_definition = ecs.FargateTaskDefinition(self, 'TaskDefinition')

        # Add our grafana container to the task definition
        container = task_definition.add_container('AppContainer',
            image=ecs.ContainerImage.from_registry("grafana/grafana"),
        )

        # Our container runs on port 3000 so we need to overwrite that
        container.add_port_mappings(ecs.PortMapping(container_port=3000))

        # Grafana service.
        service = ecs_patterns.ApplicationLoadBalancedFargateService(self, "MyGrafanaService",
            cluster=cluster,
            task_definition=task_definition,
            desired_count=1,
            public_load_balancer=True,
        )

        # Our grafana container returns a 302 redirect for GET / so we need to make that an acceptable
        # return code for our health check on the target groups.
        service.target_group.configure_health_check(
            healthy_http_codes="200-399",
        )