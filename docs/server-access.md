# Server and network information

- SSH internal address: 202.116.2.136, port 22; ordinary account: Liuchenyu.
- Independent checkout: /data1/Liuchenyu/bioduet/project.
- Repository: https://github.com/Liucy8849/BioDuet.git.
- SSH credentials are held by the existing Windows secure credential store; passwords and private keys are not included in this repository.
- Windows may have proxy/multiple-interface effects. The working direct connection used the current WLAN interface for that socket only. On November 2 its observed index was 11 and IPv4 address 10.35.45.167; these values are dynamic, not permanent settings. No global route/proxy changes were made.
- The old public FRP endpoint is unavailable. The current connection uses the internal endpoint. External access would need a separately confirmed path; no automatic fallback route is configured here.
- SSH access does not imply public website access.
- The server is shared. Historical host inventory was 144 logical CPUs and about 503 GiB physical RAM, not exclusive resources. New evaluation resource budgets and environments have not been set up in this checkout.
- API credentials, scientific datasets, model weights and SDK/R environments have not been copied into the new project. There is no claim that native/model/scientific execution is ready simply because the source checkout exists.
- Windows Git uses its existing Git Credential Manager through credential.helper=manager. The server can anonymously fetch the public source branch. No credential export is needed for this source transfer.
- Do not operate production databases, unrelated jobs, or original upstream repositories.
