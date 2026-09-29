#!/usr/bin/env bash
#
# One-shot launcher. Run it inside AWS CloudShell (the terminal icon in the
# console's bottom-left), which is already logged into your account:
#
#   curl -fsSL https://raw.githubusercontent.com/Magnus0320/Lost-and-Found-Management-System/main/deploy/aws-launch.sh | bash -s -- you@example.com
#
# It creates a spending alert, a firewall (security group), and one Ubuntu
# server that runs deploy/bootstrap-ec2.sh on first boot. Safe to re-run: it
# reuses anything that already exists.
set -euo pipefail

ALERT_EMAIL="${1:?Pass your email: ... | bash -s -- you@example.com}"
export AWS_REGION="${AWS_REGION:-ap-south-1}"   # Mumbai -- closest to India
export AWS_DEFAULT_REGION="$AWS_REGION"
NAME=lostfound
BOOTSTRAP_URL="https://raw.githubusercontent.com/Magnus0320/Lost-and-Found-Management-System/main/deploy/bootstrap-ec2.sh"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
say "Account $ACCOUNT_ID, region $AWS_REGION"

# --- 1. Spending alert ----------------------------------------------------
# Counts usage *before* credits, so it warns you when the server is burning
# credits faster than expected (~\$15/month), not only once credits are gone.
say "Budget alert: email $ALERT_EMAIL if monthly usage passes \$20"
if aws budgets describe-budget --account-id "$ACCOUNT_ID" --budget-name "$NAME-monthly" >/dev/null 2>&1; then
	echo "already exists"
else
	aws budgets create-budget --account-id "$ACCOUNT_ID" \
		--budget "{\"BudgetName\":\"$NAME-monthly\",\"BudgetLimit\":{\"Amount\":\"20\",\"Unit\":\"USD\"},\"TimeUnit\":\"MONTHLY\",\"BudgetType\":\"COST\",\"CostTypes\":{\"IncludeCredit\":false}}" \
		--notifications-with-subscribers "[{\"Notification\":{\"NotificationType\":\"ACTUAL\",\"ComparisonOperator\":\"GREATER_THAN\",\"Threshold\":100,\"ThresholdType\":\"PERCENTAGE\"},\"Subscribers\":[{\"SubscriptionType\":\"EMAIL\",\"Address\":\"$ALERT_EMAIL\"}]}]" &&
		echo "created" ||
		echo "WARNING: could not create the budget -- add one by hand under Billing > Budgets"
fi

# --- 2. Firewall ----------------------------------------------------------
# Web traffic from anywhere. SSH only from AWS's "EC2 Instance Connect"
# service, i.e. the Connect button in the console -- so there is no key file
# to lose and port 22 is not open to the internet.
say "Security group"
VPC_ID=$(aws ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text)
SG_ID=$(aws ec2 describe-security-groups \
	--filters "Name=group-name,Values=$NAME-sg" "Name=vpc-id,Values=$VPC_ID" \
	--query 'SecurityGroups[0].GroupId' --output text)
if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
	SG_ID=$(aws ec2 create-security-group --group-name "$NAME-sg" \
		--description "Lost and Found: web from anywhere, SSH via Instance Connect" \
		--vpc-id "$VPC_ID" --query GroupId --output text)
	for port in 80 443; do
		aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
			--protocol tcp --port "$port" --cidr 0.0.0.0/0 >/dev/null
	done
	EIC_PL=$(aws ec2 describe-managed-prefix-lists \
		--filters "Name=prefix-list-name,Values=com.amazonaws.$AWS_REGION.ec2-instance-connect" \
		--query 'PrefixLists[0].PrefixListId' --output text)
	aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
		--ip-permissions "IpProtocol=tcp,FromPort=22,ToPort=22,PrefixListIds=[{PrefixListId=$EIC_PL,Description=EC2-Instance-Connect}]" >/dev/null
	echo "created $SG_ID"
else
	echo "reusing $SG_ID"
fi

# --- 3. Server ------------------------------------------------------------
say "Server"
INSTANCE_ID=$(aws ec2 describe-instances \
	--filters "Name=tag:Name,Values=$NAME-server" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
	--query 'Reservations[0].Instances[0].InstanceId' --output text)

if [ "$INSTANCE_ID" = "None" ] || [ -z "$INSTANCE_ID" ]; then
	AMI_ID=$(aws ssm get-parameter \
		--name /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
		--query Parameter.Value --output text)

	TYPE=t3.micro
	if [ "$(aws ec2 describe-instance-types --instance-types t3.micro \
		--query 'InstanceTypes[0].FreeTierEligible' --output text)" != "True" ]; then
		TYPE=t2.micro
	fi
	echo "Ubuntu 24.04 ($AMI_ID) on $TYPE"

	curl -fsSL "$BOOTSTRAP_URL" -o /tmp/bootstrap-ec2.sh

	INSTANCE_ID=$(aws ec2 run-instances \
		--image-id "$AMI_ID" --instance-type "$TYPE" \
		--security-group-ids "$SG_ID" \
		--user-data file:///tmp/bootstrap-ec2.sh \
		--block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=30,VolumeType=gp3,DeleteOnTermination=true}' \
		--metadata-options HttpTokens=required \
		--tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME-server}]" \
		--query 'Instances[0].InstanceId' --output text)
	echo "launched $INSTANCE_ID"
else
	echo "reusing $INSTANCE_ID"
	aws ec2 start-instances --instance-ids "$INSTANCE_ID" >/dev/null 2>&1 || true
fi

aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"
IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
	--query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

say "Done"
cat <<MSG
Server IP:  $IP
Instance:   $INSTANCE_ID  ($AWS_REGION)

The server is now installing everything by itself (5-10 minutes).
When it finishes, http://$IP/app/ will show the app.

To watch progress: EC2 console > Instances > $NAME-server > Connect >
EC2 Instance Connect > Connect, then run:
    sudo tail -f /var/log/cloud-init-output.log
MSG
