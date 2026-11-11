# Deploying to AWS

This project deploys automatically from GitHub Actions whenever CI passes on `main`.
GitHub authenticates to AWS with short-lived **OIDC** credentials — no access keys are stored anywhere.

Setup takes about 15 minutes and only has to be done once.

## 1. AWS account

1. Create an account at [aws.amazon.com/free](https://aws.amazon.com/free).
   - **Free plan:** you can't be charged, but the account closes after 6 months (or when the credits run out) unless you upgrade. Fine for trying the project out.
   - **Paid plan:** pay-as-you-go after the credits, with an optional monthly spend limit. Choose this to keep the project running long-term; add a **Budgets** alert (e.g. $5) so you hear about any charge early.
2. Turn on **MFA** for the root user: search **IAM**, then *Security recommendations → Add MFA*.
3. Pick a region and use it everywhere below. This project defaults to **ca-central-1 (Canada Central)** — select it in the region menu at the top right of the console before creating anything.

**Expected cost:** Lambda runs ~2,900 times a month for a few hundred milliseconds each, and DynamoDB stores a few hundred thousand small items a year. Both stay within the AWS ongoing free allowances; the read API uses a Lambda Function URL instead of API Gateway to avoid its charges. Concurrency on the public API is capped at 5 to limit any traffic spike.

## 2. Create the GitHub deploy role (one click)

1. Download [`infra/github-deploy-role.yaml`](../infra/github-deploy-role.yaml) (*Download raw file* on GitHub).
2. Open **CloudFormation → Create stack → With new resources (standard) → Upload a template file** and choose it.
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

Go to **Actions → Deploy → Run workflow**. The workflow builds and deploys the stack, runs the collector once so there is data straight away, and smoke-tests the public API. After a few minutes the run summary shows the API URL.

- If you set `ALERT_EMAIL`, AWS sends a subscription confirmation email — click the link to start receiving alerts.
- From then on, every push to `main` that passes CI deploys automatically.

## Checking it works

```bash
curl "<ApiUrl>crossings"                                   # latest wait at every crossing
curl "<ApiUrl>crossings/ambassador-bridge/history"         # the last 24 hours
```

The collector runs every 15 minutes, so history starts filling in right away.

To see it on the status page, run `python -m http.server -d site 8000` and open `http://localhost:8000/?api=<ApiUrl>`, or set `window.BORDER_WAIT_API` in `site/config.js`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Deploy job is **skipped** | `AWS_DEPLOY_ROLE_ARN` isn't set as a repository *variable* (not a secret). |
| `Not authorized to perform sts:AssumeRoleWithWebIdentity` | The environment must be named exactly `production`, and `GitHubRepo` in the role stack must match `owner/repo`. |
| `EntityAlreadyExists` for the OIDC provider | Your account already has it: update the role stack with `CreateOidcProvider=false`. |
| Role stack ends in `ROLLBACK_COMPLETE` | Delete that stack and create it again; the *Events* tab shows the first error. |

## Turning it off

- Pause collection without deleting anything: redeploy with `CollectorScheduleState=DISABLED`.
- Remove everything: delete the `border-wait-live` stack in CloudFormation. The DynamoDB table is kept (deletion policy `Retain`) so collected data isn't lost by accident — delete it manually if you no longer need it.
