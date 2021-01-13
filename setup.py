import setuptools


with open("README.md") as fp:
    long_description = fp.read()


setuptools.setup(
    name="cdk_ecs_windows_fsx",
    version="0.0.1",

    description="cdk_ecs_windows_fsx",
    long_description=long_description,
    long_description_content_type="text/markdown",

    author="author",

    package_dir={"": "cdk_ecs_windows_fsx"},
    packages=setuptools.find_packages(where="cdk_ecs_windows_fsx"),

    install_requires=[
        "aws-cdk.core==1.84.0",
        "aws-cdk.aws_ec2==1.84.0",
        "aws-cdk.aws_ecs==1.84.0",
        "aws-cdk.aws_iam==1.84.0",
        "aws-cdk.aws_elasticloadbalancingv2==1.84.0",
        "aws-cdk.aws_ecs_patterns==1.84.0",
        "aws-cdk.aws_ecr==1.84.0",
        "aws-cdk.aws_logs==1.84.0",
        "aws-cdk.aws_autoscaling==1.84.0",
        "aws-cdk.aws_route53==1.84.0",
        "aws_cdk.aws_secretsmanager==1.84.0",
        "aws_cdk.aws_directoryservice==1.84.0",
        "aws_cdk.aws_fsx==1.84.0",
        "aws_cdk.custom_resources==1.84.0",
        "boto3==1.16.22",
        "simplejson==3.17.2"
    ],

    python_requires=">=3.6",

    classifiers=[
        "Development Status :: 4 - Beta",

        "Intended Audience :: Developers",

        "License :: MIT-0",

        "Programming Language :: JavaScript",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",

        "Topic :: Software Development :: Code Generators",
        "Topic :: Utilities",

        "Typing :: Typed",
    ],
)
