import os
import random
import logging
import string
from datetime import datetime, timezone, timedelta
import json
from typing import Dict

from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.resource.resources.models import ResourceGroup
import azure.functions as func
from msrestazure.azure_active_directory import MSIAuthentication
from azure.common.credentials import get_azure_cli_credentials

def formatted_time():
    return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()

def filter_for_delete(rg, rg_prefix):
    try:
        logging.debug("Checking ResourceGroup %s for deletion", rg.name)
        if not rg.name.startswith(rg_prefix): return False
        if rg.tags is None: return False
        logging.debug("  ResourceGroup %s has tags %s", rg.name, rg.tags)
        if "DeleteBy" not in rg.tags: return False
        deleteBy = datetime.fromisoformat(rg.tags["DeleteBy"])
        return deleteBy < datetime.now(deleteBy.tzinfo)
    except:
        return False

def main(mytimer: func.TimerRequest) -> None:
    """main is run from the timer function

    Args:
        mytimer (func.TimerRequest): [description]
    """
    logging.info('RandomDeployCleanup started at %s', formatted_time())
    subscription_id = None
    if "MSI_ENDPOINT" in os.environ:
        credentials = MSIAuthentication()
    else:
        credentials, subscription_id = get_azure_cli_credentials()

    rg_prefix = os.environ.get('RANDOM_DEPLOY_RESOURCEGROUP_PREFIX', "randomdeploy-")
    subscription_id = os.environ.get('RANDOM_DEPLOY_SUBSCRIPTION_ID', subscription_id)
    logging.info('Using subscription %s', subscription_id)

    with ResourceManagementClient(credentials, subscription_id) as rm_client:
        for rg in filter(lambda rg: filter_for_delete(rg, rg_prefix), rm_client.resource_groups.list()):
            logging.info(f'Deleting {rg}')
            rm_client.resource_groups.delete(rg.name)

    logging.info('RandomDeployCleanup done at %s', formatted_time())

if __name__ == "__main__":
    # Run for test
    import io, sys

    logger=logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler(stream=sys.stdout))

    main(None) #func.TimerRequest(past_due = False))
