# Overview

RandomDeploy and RandomDeployCleanup are two Azure Functions which can be used to deploy an ARM-Template with randomly generated values.
All values are taken from the parameter section.

Two environment variables are used for configuration:
- RANDOM_DEPLOY_SUBSCRIPTION_ID - The subscription ID to be used for deployments
- RANDOM_DEPLOY_LIFETIME - Time to live in seconds for a deployment, this will be used to tag the resource group with a "DeleteBy"-tag and RandomDeployCleanup will delete the whole resource group when this time has passed

The function needs to have a MSI assigned with permissions to deploy the templates. 

## RandomDeploy
This is a timer triggered function, which takes a template as a second input.

```json
{
  "scriptFile": "randomdeploy.py",
  "bindings": [
    {
      "name": "mytimer",
      "type": "timerTrigger",
      "direction": "in",
      "schedule": "0 */10 * * * *"
    },
    {
      "name": "template",
      "direction": "in",
      "type": "blob",
      "path": "templates/azuredeploy-storage.json",
      "connection": "AzureWebJobsStorage"
    }
  ]
}
```
It will take the template and fill in all parameters of type int, string and bool.
The following will be applied to fill out all entries:
1. When "allowedValues" is set, a random entry will be picked.
2. For booleans, true or false are picked by random, unless defaultValue is set
3. For integers a number between minValue and maxValue is chosen at random
4. For strings, defaultValue is parsed for template strings
    * <RANDOM_STORAGE_NAME> - will be replaced by a storage-safe name
    * <RANDOM_STRING> - replaced with a string, based on haikunator, this will honor maxLength and minLength
5. Everything else will be just passed through

If there is a parameter region, you can use this to define the region the template gets deployed into, otherwise it will default to "westus". Use "allowedValues" to pick a region randomly.

The resourcegroup will be tagged with DeleteBy and CreatedAt tags.

## RandomDeployCleanup

This function looks at all resource groups with a defined prefix (randomdeploy- by default) and deletes every resource group which is tagged with a DeleteBy time which already has passed.

```json
{
  "scriptFile": "randomdeploycleanup.py",
  "bindings": [
    {
      "name": "mytimer",
      "type": "timerTrigger",
      "direction": "in",
      "schedule": "0 */30 * * * *"
    }
  ]
}
```