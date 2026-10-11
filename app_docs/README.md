# Category Blocking

This sample is designed to show how to use URL Filtering in Falcon Foundry. It contains a few capabilities:

1. Python functions:
   - **urlblock**: Fetches host groups information
   - **create-rule**: Creates a firewall policy and rule group that block the selected categories
   - **list-policies**: Lists the policies created by the app
   - **update-policy**: Replaces a policy's categories and whitelist
   - **delete-policy**: Deletes a policy, its rule group and its stored relationships
   - **simulate-policy**: Checks whether a domain would be blocked by any category
   - **check-enforcement** / **health-check**: Verify that policies are enabled and enforcing
   - **domain-analytics**: Generates domain analytics information (optional `?days=` look-back window, 1-90, default 15)
   - **import-csv**: Transforms category domain CSV into collections
   - **list-categories**: Lists available categories
   - **search-categories**: Searches for specific categories
   - **manage-category**: Creates or updates categories

2. Collections for data storage:
   - **domain**: Stores URLs and category mappings
   - **relationship**: Stores relationship information about host groups, rule groups, and categories

3. UI Pages with React components:
   - **Category Blocking Policy**: Main interface for creating firewall rules
   - **Custom Categories**: Management of domain categories
   - **Domain Analytics**: Visualization of domain data
   - **Firewall Rules**: Management of firewall blocking rules

## Application Setup

A fresh install has no categories. Go to the Custom Categories page and import a CSV file (`category,url`; the `url` column holds one domain or a `;`-separated list), or add categories manually.

To get started quickly, import [`sample-categories.csv`](https://github.com/CrowdStrike/foundry-sample-category-blocking/blob/main/sample-categories.csv) from the GitHub repository. It contains 54 ready-to-use categories (Games, Social Media, Warez, ...).

## Usage

After installing the app, follow these steps to get started:

1. **Creating URL Categories**
   - Navigate to the **Custom Categories** page
   - Use "Import CSV" to import from a CSV file, or manually add categories
   - View and manage your categories from this interface

2. **Creating Blocking Rules**
   - Navigate to the **Category Blocking Policy** page
   - Enter a policy name and select a host group
   - Select the categories you want to block
   - Click "Preview Domains" to see what will be blocked
   - Click "Create blocking rule" to deploy the rule

3. **Viewing Analytics**
   - Navigate to the **Domain Analytics** page
   - View tables and statistics about blocked domains
   - Analyze patterns and effectiveness of your blocking rules

4. **Managing Policies**
   - Navigate to the **Firewall Rules** page
   - Edit a policy's categories and whitelist, or delete it

The source code for this app can be found on GitHub: <https://github.com/CrowdStrike/foundry-sample-category-blocking>.
