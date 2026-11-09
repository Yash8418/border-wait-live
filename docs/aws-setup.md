# Deploying to AWS

This project deploys automatically from GitHub Actions whenever CI passes on `main`.
GitHub authenticates to AWS with short-lived **OIDC** credentials — no access keys are stored anywhere.

Setup takes about 15 minutes and only has to be done once.

## 1. AWS account and a cost alert

1. Create an account at [aws.amazon.com/free](https://aws.amazon.com/free). Choose the **Paid plan** — the Free plan closes the account after 6 months. New accounts receive credits that cover far more than this project uses.
2. In **Billing → Budgets**, create a monthly cost budget of **$5** with an email alert at 80%.
3. Pick a region and use it everywhere below. This project defaults to **ca-central-1 (Canada Central)**.

**Expected cost:** Lambda runs ~2,900 times a month for a few hundred milliseconds each, and DynamoDB stores a few hundred thousand small items a year. Both stay within the AWS ongoing free allowances; the read API uses a Lambda Function URL instead of API Gateway to avoid its charges. Concurrency on the public API is capped at 5 to limit any traffic spike.

## 2. Create the GitHub deploy role (one click)

1. Open **CloudFormation → Create stack → With new resources**.
2. Upload [`infra/github-deploy-role.yaml`](../infra/github-deploy-role.yaml).
3. Stack name: `border-wait-live-github-role`. Leave the defaults (set `CreateOidcProvider` to `false` only if your account already has a `token.actions.githubusercontent.com` identity provider).
4. Tick **"I acknowledge that AWS CloudFormation might create IAM resources"** and create the stack.
5. When it finishes, copy the **`DeployRoleArn`** from the **Outputs** tab.

The role can only be assumed by this repository's `production` environment, and only has the permissions needed to manage this stack.

## 3. Connect the repository

In the GitHub repository, open **Settings**:

1. **Environments → New environment** → name it `production`. (Optionally add yourself as a required reviewer so every deploy waits for your approval.)
2. **Secrets and variables → Actions → Variables** → add:

| Variable | Value |
|---|---|
| `AWS_DEPLOY_ROLE_ARN` | the `DeployRoleArn` from step 2 |
| `AWS_REGION` | e.g. `ca-central-1` |
| `ALERT_EMAIL` | *(optional)* email for collector-failure alerts |

## 4. Deploy

Go to **Actions → Deploy → Run workflow**. After a few minutes the run summary shows the API URL.

- If you set `ALERT_EMAIL`, AWS sends a subscription confirmation email — click the link to start receiving alerts.
- From then on, every push to `main` that passes CI deploys automatically.

## Checking it works

```bash
curl "<ApiUrl>crossings"                                   # latest wait at every crossing
curl "<ApiUrl>crossings/ambassador-bridge/history"         # the last 24 hours
```

The collector runs every 15 minutes, so history starts filling in right away.

## Turning it off

- Pause collection without deleting anything: redeploy with `CollectorScheduleState=DISABLED`.
- Remove everything: delete the `border-wait-live` stack in CloudFormation. The DynamoDB table is kept (deletion policy `Retain`) so collected data isn't lost by accident — delete it manually if you no longer need it.
