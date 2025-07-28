# Repository Setup

When you create a new repo with this template, you still need to do a few things before making it public.

1. Find and replace `$REPOSITORY_NAME` with the name of the new repository in all files.
2. Find and replace `$SAMPLE_NAME` with the name in `manifest.yml`. 
3. Update the following sections in the main `README.md`:
    * Description
    * Prerequisites
    * Getting Started: make sure permissions and last paragraph are correct
    * About this sample app
4. Remove id values in the `manifest.yml` by changing them all to `""` or use the following script to remove them. 

   ```shell
   yq -i 'del(.. | select(has("id")).id) | del(.. | select(has("app_id")).app_id)' manifest.yml
   ```
   
5. In `.github/dependabot.yml`, remove the ecosystems your app is missing. For example, if it only has a Python function, it should be as follows:

    ```yaml
    version: 2
    updates:
      - package-ecosystem: pip
        directory: "/functions/path-to-your-function/"
        schedule:
          interval: weekly
      - package-ecosystem: github-actions
        directory: "/"
        schedule:
          interval: weekly
    ```

6. In the `.github/workflows` directory, create a `main.yml` that resembles one of the other samples:

   - **foundry-sample-mitre**: [`main.yml`](https://github.com/CrowdStrike/foundry-sample-mitre/blob/main/.github/workflows/main.yml) builds extensions and pages with Yarn. It also has a [`rebuild.yml`](https://github.com/CrowdStrike/foundry-sample-mitre/blob/main/.github/workflows/rebuild.yml) that recreates the UI bits with the latest dependencies every week. 
   - **foundry-sample-rapid-response**: [`main.yml`](https://github.com/CrowdStrike/foundry-sample-rapid-response/blob/main/.github/workflows/main.yml) compiles Go functions and builds/tests UI pages.
   - **foundry-sample-ngsiem-importer**: [`main.yml`](https://github.com/CrowdStrike/foundry-sample-ngsiem-importer/blob/main/.github/workflows/main.yml) installs Python dependencies, runs unit tests, and confirms the function starts successfully. 

7. In the GitHub UI, update the **About** section to be `$SAMPLE_NAME sample Foundry app`. Add `falcon-foundry` as a topic and uncheck Releases, Packages, and Deployments.
8. Go to **Settings** and uncheck the **Wikis** and **Projects** features.
9. In **Collaborators and teams**, add the **CrowdStrike/foundry** and **CrowdStrike/solution-architects** teams with **Role: admin**. Remove your personal account if you're a member of the foundry team.
10. In **Branches**, add a **classic** branch protection rule:

     - Branch name pattern: `main`
     - Check **Require a pull request before merging**
     - Check **Require linear history**

Once you've completed these updates, delete this file. Its location is at `.github/README.md`.
