from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_ecs_patterns as ecs_patterns
from aws_cdk import aws_efs as efs
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_logs as logs
from aws_cdk import aws_route53 as route53
# For consistency with other languages, `cdk` is the preferred import name for
# the CDK's core module.  The following line also imports it as `core` for use
# with examples from the CDK Developer's Guide, which are in the process of
# being updated to use `cdk`.  You may delete this import if you don't need it.
from aws_cdk import core
from aws_cdk import core as cdk


class GrafanaEcsStack(cdk.Stack):

    def __init__(self, scope: cdk.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # DNS domain_name for our service
        hosted_zone = cdk.CfnParameter(self, "hostedZone", type="String", default="example.org")
        hosted_zone_id = cdk.CfnParameter(self, "hostedZoneId", type="String", default="")
        hosted_name = cdk.CfnParameter(self, "hostedName", type="String", default="grafana")

        # Create a VPC with all the defaults CDK uses
        vpc = ec2.Vpc(self, "GrafanaVPC", max_azs=3)

        # Create an ECS cluster with all the defaults from CDK
        cluster = ecs.Cluster(self, "GrafanaCluster", vpc=vpc)

        # EFS for persistent storage
        #
        # Files are transitioned to infrequent access (IA) storage after 14 days
        file_system = efs.FileSystem(self, "GrafanaFileSystem",
            vpc=vpc,
            lifecycle_policy=efs.LifecyclePolicy.AFTER_14_DAYS,
            performance_mode=efs.PerformanceMode.GENERAL_PURPOSE
        )

        # Task definition
        task_definition = ecs.FargateTaskDefinition(self, 'TaskDefinition',
            memory_limit_mib=1024,
            cpu=512
        )

        # # Add our EFS volume to the task definition
        # task_definition.add_volume(
        #     name="data",
        #     efs_volume_configuration=ecs.EfsVolumeConfiguration(
        #         file_system_id=file_system.file_system_id,
        #     )
        # )

        loggroup = logs.LogGroup(self, "GrafanaLogGroup",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # Add our grafana container to the task definition
        container = task_definition.add_container('AppContainer',
            image=ecs.ContainerImage.from_registry("grafana/grafana"),
            logging=ecs.LogDriver.aws_logs(
                stream_prefix="grafana",
                log_group=loggroup,
            ),
        )

        # Our container runs on port 3000 so we need to overwrite that
        container.add_port_mappings(ecs.PortMapping(container_port=3000))
        # container.add_mount_points(ecs.MountPoint(
        #     container_path="/data",
        #     read_only=False,
        #     source_volume="data"
        # ))

        # Load our already existing Route53 zone
        route53_domain = route53.HostedZone.from_hosted_zone_attributes(self, "HostedZone",
            hosted_zone_id=hosted_zone_id.value_as_string,
            zone_name=hosted_zone.value_as_string,
        )

        # SSL Certificate
        certificate = acm.Certificate(self, "Certificate",
            domain_name=f"{hosted_name.value_as_string}.{hosted_zone.value_as_string}",
            validation=acm.CertificateValidation.from_dns(route53_domain)
        )

        # Grafana service.
        service = ecs_patterns.ApplicationLoadBalancedFargateService(self, "MyGrafanaService",
            cluster=cluster,
            task_definition=task_definition,
            desired_count=1,
            public_load_balancer=True,
            redirect_http=True,
            certificate=certificate,

            # Providing the DNS name and zone here will create the A ALIAS record in Route53
            domain_name=f"{hosted_name.value_as_string}.{hosted_zone.value_as_string}",
            domain_zone=route53_domain,
        )

        # Make sure our containers have access to the EFS
        file_system.grant(service.task_definition.obtain_execution_role(), "elasticfilesystem:ClientWrite")

        # Our grafana container returns a 302 redirect for GET / so we need to make that an acceptable
        # return code for our health check on the target groups.
        service.target_group.configure_health_check(
            healthy_http_codes="200-399",
        )
