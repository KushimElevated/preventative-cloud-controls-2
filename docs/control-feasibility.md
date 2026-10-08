# Provider feasibility and evidence

Checked 2026-10-08. Sources establish provider behavior, not enterprise enablement or a successful deployment. The MVP remains **DEMO / REVIEW_ONLY** even when a template is recognized.

## Azure AI Search

The seeded assignment proposal references built-in definition `ee980b6d-0eca-4501-8d54-f6290fd512c3`, version `1.0.1`. Official source matches `Microsoft.Search/searchServices` with `publicNetworkAccess` not equal to `Disabled`. It supports Audit, Deny and Disabled. The supported MVP template fixes effect `Deny` and `enforcementMode=Default`; a different document needs another reviewed evaluator.

Inventory collection omissions are UNKNOWN in our assessment, even if a live policy engine can evaluate the full provider object. Resource-management deny affects relevant create/update requests, not remediation of existing public services. Private endpoint, DNS and client connectivity are prerequisites for remediation and require separate evidence.

- [Official built-in source](https://github.com/Azure/azure-policy/blob/master/built-in-policies/policyDefinitions/Search/RequirePublicNetworkAccessDisabled_Deny.json)
- [Policy index](https://learn.microsoft.com/en-us/azure/search/policy-reference)
- [Deny behavior](https://learn.microsoft.com/en-us/azure/governance/policy/concepts/effect-deny)
- [Exemption assignment linkage and expiry](https://learn.microsoft.com/en-us/azure/governance/policy/concepts/exemption-structure)

Native Azure exemption objects can retain their identity after expiration while no longer being honored. The mock reference identifies an assignment/exemption; nothing is sent to Azure. Exported exception records must be mapped to exact live assignments by the future Cloud Engineering adapter before operational use.

## AWS S3

The fixture SCP denies `s3:PutAccountPublicAccessBlock` on `*`, following the account safeguard protection pattern documented by AWS Managed Services. This restriction prevents changes; it does not establish safe account settings. All four account Block Public Access settings must already be observed true. It can also block legitimate administrative changes, so recovery must be reviewed.

The evaluator covers ordinary member-account principal fixtures only. Management-account and service-linked-role requests are unknown/outside this prediction. There is no Audit SCP effect. An inherited explicit deny cannot be undone by a lower-scope allow; the demo does not provide a general authorization-policy interpreter.

- [AWS safeguard example, SCP-AMS-018](https://docs.aws.amazon.com/managedservices/latest/userguide/scp-library-compliance.html)
- [S3 Block Public Access and combined levels](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html)
- [SCP behavior and coverage](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html)
- [SCP inheritance](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps_evaluation.html)
- [Policy simulator limitations](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_testing-policies.html)

Only synthetic general-purpose bucket records with account configuration evidence are evaluated. Access-point policy analysis, directory buckets, resource-based policy evaluation, access-path simulation and account configuration changes are outside this MVP. Bucket-level exemption requests are unsupported by this account-wide protection template.

[Organizations S3 policies](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_s3.html) are a native centralized Block Public Access alternative to evaluate with Cloud Engineering. This code does not implement or assume adoption of that mechanism.
