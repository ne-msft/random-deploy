import os
import random
import logging
import string
import datetime
import json
from typing import Dict
from haikunator import Haikunator

from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.resource.resources.models import DeploymentMode, Deployment, DeploymentProperties, ResourceGroup
import azure.functions as func
from msrestazure.azure_active_directory import MSIAuthentication
from azure.common.credentials import get_azure_cli_credentials

class RandomDeployer(object):
    haikunator = Haikunator()

    def __init__(self,
            subscription: str,
            credentials: object,
            template: Dict[str, str],
            resourceGroupPrefix: str = "randomdeploy-",
            defaultRegion: str = "westus"):
        self.subscription = subscription
        self.credentials = credentials
        self.template = template
        self.resourceGroupPrefix = resourceGroupPrefix
        self.logger = logging.getLogger("RandomDeploy")
        self.defaultRegion = defaultRegion

    def __fill_variables(self, parameters: Dict[str, Dict[str, str]]):
        filled_variables = dict()
        for (k, v) in parameters.items():
            pick = None
            if "allowedValues" in v:
                # allowedValues take precedence, because we'll have to pass one of those for a valid template
                pick = random.choice(v["allowedValues"])
            elif (v["type"] == "bool" and "defaultValue" not in v):
                # Only pick random bool when there was NO defaultValue
                pick = random.choice((True, False))
            elif (v["type"] == "int" and "defaultValue" not in v):
                # For integers we pick something between and inclusive minValue and maxValue, unless a default was given
                minVal = v.get("minValue", 0)
                maxVal = v.get("maxValue", 2**64)
                pick = random.randint(minVal, maxVal)
            elif (v["type"] == "string"):
                # Strings will use defaultValue as a template and honor minLength and maxLength
                pick = str(v.get("defaultValue", "<RANDOM_STORAGE_STRING>"))
                minLength = int(v.get("minLength", 8))
                if pick.find("<RANDOM_STORAGE_NAME>") >= 0:
                    pick=pick.replace("<RANDOM_STORAGE_NAME>", self.haikunator.haikunate(delimiter="", token_length=minLength, token_chars=string.ascii_lowercase+string.digits))
                if pick.find("<RANDOM_STRING>") >= 0:
                    pick=pick.replace("<RANDOM_STRING>", self.haikunator.haikunate(token_length=8, token_chars=string.ascii_lowercase+string.digits))
                if "maxLength" in v:
                    pick=pick[:v["maxLength"]]
            else:
                pick = str(v.get("defaultValue"))
            filled_variables[k] = {"value": pick}
        self.logger.debug("Generated variables: %s", filled_variables)
        return filled_variables

    def deploy(self, lifetime: int = 60*60*24):
        with ResourceManagementClient(self.credentials, self.subscription) as rm_client:
            resourceGroup = self.resourceGroupPrefix + self.haikunator.haikunate(token_length=16)
            filledVariables = self.__fill_variables(self.template.get("parameters", dict()))
            region = self.defaultRegion
            if "region" in filledVariables:
                region = filledVariables["region"]["value"]
            self.logger.info("Deploying to region %s and RG %s", region, resourceGroup)
            if rm_client.resource_groups.check_existence(resourceGroup):
                raise Exception(f"Resourcegroup named '{resourceGroup}' already exists")

            createdOn = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
            deleteBy = createdOn + datetime.timedelta(seconds = lifetime)

            rm_client.resource_groups.create_or_update(resourceGroup,
                ResourceGroup(
                    location = region,
                    tags = {
                        'DeleteBy': deleteBy.isoformat(),
                        'CreatedOn': createdOn.isoformat(),
                    }
                )
            )

            return rm_client.deployments.create_or_update(
                resourceGroup,
                "deploy-" + resourceGroup,
                Deployment(properties =
                    DeploymentProperties(
                        mode = DeploymentMode.incremental,
                        template = self.template,
                        parameters = filledVariables
                    )
                )
            )

def formatted_time():
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()

def main(mytimer: func.TimerRequest, template: func.InputStream) -> None:
    """main is run from the timer function

    Args:
        mytimer (func.TimerRequest): [description]
    """
    logging.info('RandomDeployer started at %s', formatted_time())
    subscription_id = None
    if "MSI_ENDPOINT" in os.environ:
        credentials = MSIAuthentication()
    else:
        credentials, subscription_id = get_azure_cli_credentials()

    subscription_id = os.environ.get('RANDOM_DEPLOY_SUBSCRIPTION_ID', subscription_id)
    logging.info('Using subscription %s', subscription_id)

    deployer = RandomDeployer(subscription_id, credentials, json.load(template))
    deployer.deploy(int(os.environ.get('RANDOM_DEPLOY_LIFETIME', 60*60*24)))

    logging.info('RandomDeployer done at %s', formatted_time())

if __name__ == "__main__":
    # Run for test
    import io, sys

    logger=logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler(stream=sys.stdout))
    os.environ["RANDOM_DEPLOY_LIFETIME"] = str(60*60)

    storageTemplate = io.StringIO("""
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "storageAccountName": {
      "type": "string",
      "metadata": {"description": "Specifies the name of the Azure Storage account."},
      "defaultValue": "rnddpl<RANDOM_STORAGE_NAME>",
      "maxLength": 24
    },
    "region": {
      "type": "string",
      "metadata": {"description": "Region to deploy into"},
      "allowedValues": ["centralus","eastasia","southeastasia","eastus","eastus2","westus","westus2","northcentralus","southcentralus","westcentralus","northeurope","westeurope","japaneast","japanwest","brazilsouth","australiasoutheast","australiaeast","westindia","southindia","centralindia","canadacentral","canadaeast","uksouth","ukwest","koreacentral","koreasouth","francecentral","southafricanorth","uaenorth","australiacentral","switzerlandnorth","germanywestcentral","norwayeast"]
    }
  },
  "resources": [
    {
      "type": "Microsoft.Storage/storageAccounts",
      "apiVersion": "2019-06-01",
      "name": "[parameters('storageAccountName')]",
      "location": "[parameters('region')]",
      "sku": {"name": "Standard_LRS","tier": "Standard"},
      "kind": "StorageV2",
      "properties": {"accessTier": "Hot"}
    }
  ]
}
""")
    if len(sys.argv) > 1:
        storageTemplate = open(sys.argv[1], "r")
    main(None, storageTemplate)
