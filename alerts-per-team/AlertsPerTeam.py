import requests
import json

############ OpsGenie Configuration ##############
opsGenieAPIKey = "<Your OpsGenie API Key>"
opsGenieAPIURL = "https://api.opsgenie.com"
opsGenieAlertEndPoint = "/v1/json/alert"
opsGenieAlertAddNoteEndPoint = opsGenieAlertEndPoint + "/note"
opsGenieAlertCloseEndPoint = opsGenieAlertEndPoint + "/close"
opsGenieAlertAddTagsEndPoint = opsGenieAlertEndPoint + "/tags"


# Makes a GET request to OpsGenie Alert API and returns the alert with given alert id.
def get_alert(alert_id):
    params = {
        "apiKey": opsGenieAPIKey,
        "id": alert_id
    }

    request = requests.get(opsGenieAPIURL + opsGenieAlertEndPoint, params=params)
    alert = request.json()

    return alert


# Creates sub-alerts for each team given by "teamsToNotify" in the alert details.
def create_sub_alerts(alert_description, alert_details, event):
    alert_to_create = event["alert"]
    alert_to_create["apiKey"] = opsGenieAPIKey
    alert_to_create["description"] = alert_description
    alert_to_create["details"] = alert_details

    teams_list = str(alert_details["teamsToNotify"])

    teams = teams_list.split(',')

    results = []

    for team in teams:
        team = team.strip()

        alert_to_create["teams"] = team

        if "teamsToNotify" in alert_to_create["details"]:
            del alert_to_create["details"]["teamsToNotify"]

        alert_to_create["alias"] = ""
        alert_to_create["details"]["rootAlertId"] = event["alert"]["alertId"]
        alert_to_create["user"] = "AWSLambda"  # Set the user as AWSLambda, in order to prevent loop when the
        # the callback of creating alert arrives.

        request = requests.post(opsGenieAPIURL + opsGenieAlertEndPoint, json=alert_to_create)
        result = request.json()
        results.append("Create sub-alert result for team [" + team + "]: " + json.dumps(result)
                       .decode('string_escape'))

        request_data_add_tag = {
            "apiKey": opsGenieAPIKey,
            "id": event["alert"]["alertId"],
            "tags": "subAlert:" + result["alertId"]
        }

        request_add_tag = requests.post(opsGenieAPIURL + opsGenieAlertAddTagsEndPoint, json=request_data_add_tag)
        result_add_tag = request_add_tag.json()
        results.append("Add tags to root alert result for sub-alert [" + result["alertId"] + "]: " +
                       json.dumps(result_add_tag).decode('string_escape'))

    return results


# Adds a note to the root alert when a sub-alert is acknowledged.
def add_note_to_root_alert(alert_details, event):
    root_alert_id = alert_details["rootAlertId"]

    alert = get_alert(event["alert"]["alertId"])

    team_that_acks = str(alert["teams"][0])

    request_data = {
        "apiKey": opsGenieAPIKey,
        "id": root_alert_id,
        "note": "User [" + event["alert"]["username"] + "] acknowledged the alert for team [" + team_that_acks +
                "]."
    }

    request = requests.post(opsGenieAPIURL + opsGenieAlertAddNoteEndPoint, json=request_data)

    result = request.json()

    return "Result of AddNote to Root Alert: " + str(result)


# Closes the root and the sub-alerts when either the root alert or one of the sub-alerts is closed.
def close_root_and_sub_alerts(alert_details, event):
    results = []

    if "teamsToNotify" in alert_details:
        tags = event["alert"]["tags"]

        for tag in tags:
            if str(tag).startswith("subAlert:"):
                sub_alert_id = str(tag).replace("subAlert:", "")

                request_data = {
                    "apiKey": opsGenieAPIKey,
                    "id": sub_alert_id,
                    "user": "AWSLambda"
                }

                request = requests.post(opsGenieAPIURL + opsGenieAlertCloseEndPoint, json=request_data)
                result = request.json()

                if int(result["code"]) == 21:
                    results.append("Ignoring closing sub-alert [" + sub_alert_id +
                                   "], because it was already closed.")
                else:
                    results.append("Close sub-alert result for sub-alert [" + sub_alert_id + "]: " +
                                   json.dumps(result).decode('string_escape'))
    elif "rootAlertId" in alert_details:
        root_alert_id = alert_details["rootAlertId"]
        root_alert = get_alert(root_alert_id)
        tags = root_alert["tags"]

        for tag in tags:
            if str(tag).startswith("subAlert:"):
                sub_alert_id = str(tag).replace("subAlert:", "")

                if sub_alert_id != event["alert"]["alertId"]:
                    request_data = {
                        "apiKey": opsGenieAPIKey,
                        "id": sub_alert_id,
                        "user": "AWSLambda"
                    }

                    request = requests.post(opsGenieAPIURL + opsGenieAlertCloseEndPoint, json=request_data)
                    result = request.json()

                    if int(result["code"]) == 21:
                        results.append("Ignoring closing sub-alert [" + sub_alert_id +
                                       "], because it was already closed.")
                    else:
                        results.append("Close sub-alert result for sub-alert [" + sub_alert_id + "]: " +
                                       json.dumps(result).decode('string_escape'))

        request_data_to_close_root_alert = {
            "apiKey": opsGenieAPIKey,
            "id": root_alert_id,
            "user": "AWSLambda"
        }

        request_close_root_alert = requests.post(opsGenieAPIURL + opsGenieAlertCloseEndPoint,
                                             json=request_data_to_close_root_alert)
        result_close_root_alert = request_close_root_alert.json()

        if int(result_close_root_alert["code"]) == 21:
            results.append("Ignoring closing root alert [" + root_alert_id + "], because it was already closed.")
        else:
            results.append("Close root alert [" + root_alert_id + "] result: " +
                           json.dumps(result_close_root_alert).decode('string_escape'))
    else:
        results.append("Alert is neither a root alert nor a sub-alert.")

    return results


# Entry point.
def lambda_handler(event, context):
    action = event["action"]
    alert = get_alert(event["alert"]["alertId"])
    alert_description = alert["description"]
    alert_details = alert["details"]

    if str(action).lower() == "create":
        if "teamsToNotify" in alert_details.keys() and event["alert"]["username"] != "AWSLambda":
            print str(create_sub_alerts(alert_description, alert_details, event))
        else:
            print "Ignoring Action [" + action + "] since it\'s a create action for sub-alert."
    elif str(action).lower() == "acknowledge":
        if "rootAlertId" in alert_details.keys():
            print str(add_note_to_root_alert(alert_details, event))
        else:
            print "Ignoring Action [" + action + "] since it\'s an acknowledge action for root alert."
    elif str(action).lower() == "close":
        if event["alert"]["username"] != "AWSLambda":
            print str(close_root_and_sub_alerts(alert_details, event))
        else:
            print "Ignoring close action since it's for an already closed alert."
    else:
        print "Ignoring Action [" + action + "]."
