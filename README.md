![CrowdStrike Falcon](/images/cs-logo.png?raw=true)

# Category Blocking Foundry app

This Category Blocking Foundry app provides a comprehensive URL filtering solution that simplifies firewall rule management through custom categories and automated rule deployment. Built on CrowdStrike's Foundry platform, this application streamlines URL blocking workflows while providing valuable insights into blocking patterns.

## Description

The Category Blocking app allows you to:

- Create and manage custom categories of domains for blocking
- Deploy firewall rules to block categories of domains across host groups
- Import URL categories from CSV files
- Visualize relationships between categories, rule groups, and host groups
- Generate analytics on domain blocking patterns

## Prerequisites

* Python 3.13+ (needed if modifying the app's functions). See [Python For Beginners](https://www.python.org/about/gettingstarted/) for installation instructions.
* Node.js (needed for React JS development).
* npm 9+ or Yarn (needed for managing UI dependencies). See https://yarnpkg.com/getting-started for installation instructions.
* FalconPy SDK (for CrowdStrike API integration). Install with pip install crowdstrike-falconpy

## Getting Started

Clone this repository to your local system:

```shell
git clone https://github.com/CrowdStrike/foundry-sample-url-filtering
cd foundry-sample-url-filtering
```

### Deployment Process

After cloning the repository, follow these steps to deploy the application:

1. **Login to Foundry CLI**
   ```shell
   foundry login
   ```
   This will prompt you to enter your CrowdStrike API credentials.

   <!-- Image placeholder for login process -->

2. **Deploy the application**
   ```shell
   foundry apps deploy
   ```
   This command packages and deploys your application to Foundry.

   <!-- Image placeholder for deployment process -->

3. **Install the application**
   - Navigate to the Falcon console
   - Go to **Foundry** > **App Library**
   - Find the Category Blocking app
   - Click **Install**

   <!-- Image placeholder for installation screen -->

4. **Accept permissions**
   - Review the requested permissions
   - Click **Accept** to grant the necessary permissions
   - The application requires access to firewall management, host groups, and devices

   <!-- Image placeholder for permissions screen -->

5. **Access the application**
   - Once installed, the application will be available in the Falcon console
   - Navigate to the app from the main menu

   <!-- Image placeholder for accessing the app -->

### Required permissions

This app requires the following API scopes:
- firewall-management:read
- firewall-management:write
- host-group:read
- host-group:write
- devices:read
- devices:write

## About this app

This application demonstrates advanced usage of Functions, Collections and UI Experience in Falcon Foundry, implementing several key capabilities for URL filtering and firewall management:

### Key Components

1. **Python functions with multiple handlers:**
   - **urlblock**: Fetches host groups information
   - **categories**: Retrieves categories from collections
   - **create-rule**: Creates firewall management blocking rules
   - **domain-analytics**: Generates domain analytics information
   - **import-csv**: Transforms category domain CSV into collections
   - **list-categories**: Lists available categories
   - **search-categories**: Searches for specific categories
   - **manage-categories**: Creates or updates categories
   - **manage-relationship**: Creates relationships between categories, rule groups, and hosts
   - **get-relationship**: Retrieves relationship information
   - **update-rules**: Updates existing rules with new domains

2. **Collections for data storage:**
   - **domain**: Stores URLs and category mappings
   - **relationship**: Stores relationship information about host groups, rule groups, and categories

3. **UI Pages with React components:**
   - **Home**: Main interface for creating firewall rules
   - **FirewallRules**: Management of domain categories
   - **DomainAnalytics**: Visualization of domain data
   - **Relationship**: Visualization of relationships between categories, rule groups, and host groups

### Directory structure
- **collections**: Schemas for domain and relationship collections
- **ui/pages/urlblocking**: React-based frontend application
- **functions/urlblock**: Python backend handlers

## Using the App

### Creating URL Categories
1. Navigate to the **FirewallRules** page
2. Click "Import Categories" to import from a CSV file, or manually add categories
3. View and manage your categories from this interface

### Creating Blocking Rules
1. Navigate to the **Home** page
2. Enter a policy name and select a host group
3. Select the categories you want to block
4. Click "Preview domains" to see what will be blocked
5. Click "Create blocking rule" to deploy the rule

### Viewing Analytics
1. Navigate to the **DomainAnalytics** page
2. View charts and statistics about blocked domains
3. Analyze patterns and effectiveness of your blocking rules

### Visualizing Relationships
1. Navigate to the **Relationship** page
2. Explore the connections between categories, rule groups, and host groups
3. Understand how your blocking rules are structured

## Foundry resources

- Foundry documentation: [US-1](https://falcon.crowdstrike.com/documentation/category/c3d64B8e/falcon-foundry) | [US-2](https://falcon.us-2.crowdstrike.com/documentation/category/c3d64B8e/falcon-foundry) | [EU](https://falcon.eu-1.crowdstrike.com/documentation/category/c3d64B8e/falcon-foundry)
- Foundry learning resources: [US-1](https://falcon.crowdstrike.com/foundry/learn) | [US-2](https://falcon.us-2.crowdstrike.com/foundry/learn) | [EU](https://falcon.eu-1.crowdstrike.com/foundry/learn)

---

<p align="center"><img src="/images/cs-logo-footer.png"><br/><img width="300px" src="/images/adversary-goblin-panda.png"></p>
<h3><p align="center">WE STOP BREACHES</p></h3>
