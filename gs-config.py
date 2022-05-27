# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

# CLI tool for viewing and updating AWS Ground Station mission profiles

# The tool can:
# 1. Show details about an AWS Ground Station mission profiles
# 2. Update the following AWS Ground Station mission profile parameters:
#    - Mission profile name
#    - Minimum viable contact duration
#    - Contact prepass duration
#    - Contact postpass duration
#    - Antenna tracking
#    - Uplink power

# It uses your default credentials stored in the /.aws folder

# NB: Updating a mission profile will not update the execution parameters for existing future contacts.

# boto3 GroundStation reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/groundstation.html


import regex
import json
import boto3
from botocore.config import Config
from PyInquirer import prompt, Separator
from prompt_toolkit.validation import Validator, ValidationError


def get_mission_profile_list(gs_client):

    mission_profile_list = []

    responce = gs_client.list_mission_profiles()

    mission_profile_list.append(
        Separator("               Name             --   ID      ")
    )

    if responce["missionProfileList"]:
        for profile in responce["missionProfileList"]:
            mission_profile_details = (
                str(profile["name"]).ljust(30) + "  --  " + profile["missionProfileId"]
            )
            mission_profile_list.append(mission_profile_details)
    else:
        print("No available mission profiles in this region.")
        main()

    mission_profile_list.append("Exit")

    return mission_profile_list


def view_mission_profile(gs_client, mission_profile_id, mission_profile_name):

    print("========================================================================")
    print("========================================================================")
    print("Mission Profile Name : " + mission_profile_name)
    print("Mission Profile ID : " + mission_profile_id)
    print("========================================================================")
    print("========================================================================")

    endpoint_name_list = []

    profile_data = gs_client.get_mission_profile(missionProfileId=mission_profile_id)

    print(
        "Contact pre pass duruation : "
        + str(profile_data["contactPrePassDurationSeconds"])
        + "s"
    )
    print(
        "Contact post pass duruation : "
        + str(profile_data["contactPostPassDurationSeconds"])
        + "s"
    )
    print(
        "Minimum viable contact duration : "
        + str(profile_data["minimumViableContactDurationSeconds"])
        + "s"
    )

    tracking_config_id = profile_data["trackingConfigArn"].split("/")[2]
    autotrack = gs_client.get_config(
        configId=tracking_config_id, configType="tracking"
    )["configData"]["trackingConfig"]["autotrack"]

    print("Antenna autotrack : " + autotrack)

    print("")
    print("")
    print("Data Flow Edges and their Configs:")

    for config_pair in profile_data["dataflowEdges"]:
        for config in config_pair:
            config_id = config.split("/")[2]
            config_type = config.split("/")[1]
            config_name = gs_client.get_config(
                configId=config_id, configType=config_type
            )["name"]

            print("--------------------------------------------------------------")
            print(config_type + " : " + config_name)
            print("--------------------------------------------------------------")

            if config_type == "dataflow-endpoint":
                endpoint_name = gs_client.get_config(
                    configId=config_id, configType=config_type
                )["configData"]["dataflowEndpointConfig"]["dataflowEndpointName"]
                endpoint_name_list.append(endpoint_name)

            config_data = gs_client.get_config(
                configId=config_id, configType=config_type
            )["configData"]

            if "antennaDownlinkDemodDecodeConfig" in config_data.keys():

                decode_config = json.loads(
                    config_data["antennaDownlinkDemodDecodeConfig"]["decodeConfig"][
                        "unvalidatedJSON"
                    ]
                )
                decode_json = {}
                decode_json["unvalidatedJSON"] = decode_config

                demod_config = json.loads(
                    config_data["antennaDownlinkDemodDecodeConfig"][
                        "demodulationConfig"
                    ]["unvalidatedJSON"]
                )
                demod_json = {}
                demod_json["unvalidatedJSON"] = demod_config

                combined_config = {}
                combined_config["decodeConfig"] = decode_json
                combined_config["demodulationConfig"] = demod_json
                combined_config["spectrumConfig"] = config_data[
                    "antennaDownlinkDemodDecodeConfig"
                ]["spectrumConfig"]

                jsondata = {}
                jsondata["antennaDownlinkDemodDecodeConfig"] = combined_config

                print(json.dumps(jsondata, indent=4))

            else:
                print(json.dumps(config_data, indent=4))

    dataflow_endpoint_group_list = gs_client.list_dataflow_endpoint_groups()

    selected_dataflow_endpoint_group_id = ""

    # select the DFEG associated with the mission profile
    for dataflow_endpoint_group in dataflow_endpoint_group_list[
        "dataflowEndpointGroupList"
    ]:
        dataflow_endpoint_group_id = dataflow_endpoint_group["dataflowEndpointGroupId"]
        for dataflow_endpoint in gs_client.get_dataflow_endpoint_group(
            dataflowEndpointGroupId=dataflow_endpoint_group_id
        )["endpointsDetails"]:
            dataflow_endpoint_name = dataflow_endpoint["endpoint"]["name"]
            if dataflow_endpoint_name in endpoint_name_list:
                selected_dataflow_endpoint_group_id = dataflow_endpoint_group_id
                break

    dataflow_endpoint_group_id = selected_dataflow_endpoint_group_id
    if not dataflow_endpoint_group_id:
        print(
            "There are no dataflow endpoints in this mission profile that are part of a dataflow endpoint group."
        )
        quit()

    print("")
    print("--------------------------------------------------------------")
    print("Data Flow Endpoint Group : " + dataflow_endpoint_group_id)
    print("Data Flow Endpoints in this Group:")
    print("--------------------------------------------------------------")

    for dataflow_endpoint in gs_client.get_dataflow_endpoint_group(
        dataflowEndpointGroupId=dataflow_endpoint_group_id
    )["endpointsDetails"]:
        dataflow_endpoint_name = dataflow_endpoint["endpoint"]["name"]
        dataflow_endpoint_IP = dataflow_endpoint["endpoint"]["address"]["name"]
        dataflow_endpoint_port = str(dataflow_endpoint["endpoint"]["address"]["port"])
        dataflow_endpoint_status = dataflow_endpoint["endpoint"]["status"]
        dataflow_endpoint_sg = str(
            dataflow_endpoint["securityDetails"]["securityGroupIds"]
        ).strip("[']")

        print("Name      : " + dataflow_endpoint_name)
        print("Status    : " + dataflow_endpoint_status)
        print("Sec group : " + dataflow_endpoint_sg)
        print("Target:   : " + dataflow_endpoint_IP + ":" + dataflow_endpoint_port)
        print("")

    quit()


def update_mission_profile(gs_client, mission_profile_id):

    print(
        "Updating a mission profile will not update the execution parameters for existing future contacts."
    )

    update_question = [
        {
            "type": "list",
            "name": "update",
            "message": "What would you like to update?",
            "choices": [
                "Mission profile name",
                "Uplink power",
                "Uplink center frequency",
                "DigIF Downlink center frequency",
                "DigIF Downlink bandwidth",
                "Minimum viable contact duration",
                "Contact prepass duration",
                "Contact postpass duration",
                "Antenna tracking",
                "Other",
                "Quit",
            ],
        }
    ]

    update_answer = prompt(update_question)
    update = update_answer["update"]

    if update == "Mission profile name":
        change_mission_profile(gs_client, mission_profile_id, "name")
    elif update == "Uplink center frequency":
        change_uplink_center_frequency(gs_client, mission_profile_id)
    elif update == "DigIF Downlink center frequency":
        change_downlink_center_frequency(gs_client, mission_profile_id)
    elif update == "DigIF Downlink bandwidth":
        change_downlink_bandwidth(gs_client, mission_profile_id)
    elif update == "Minimum viable contact duration":
        change_mission_profile(gs_client, mission_profile_id, "minimum contact")
    elif update == "Contact prepass duration":
        change_mission_profile(gs_client, mission_profile_id, "prepass")
    elif update == "Contact postpass duration":
        change_mission_profile(gs_client, mission_profile_id, "postpass")
    elif update == "Antenna tracking":
        change_tracking(gs_client, mission_profile_id)
    elif update == "Uplink power":
        change_uplink_power(gs_client, mission_profile_id)
    elif update == "Other":
        print(
            "Updating other parameters is best done by redploying the CloudFormation template for your AWS Ground Station configuration."
        )
        print("Exiting to main menu.")
        main()
    elif update == "Quit":
        quit()


def change_mission_profile(gs_client, mission_profile_id, parameter):

    updated_profile_data = gs_client.get_mission_profile(
        missionProfileId=mission_profile_id
    )

    if (
        parameter == "minimum contact"
        or parameter == "prepass"
        or parameter == "postpass"
    ):
        if parameter == "minimum contact":
            value = updated_profile_data["minimumViableContactDurationSeconds"]
        elif parameter == "prepass":
            value = updated_profile_data["contactPrePassDurationSeconds"]
        elif parameter == "postpass":
            value = updated_profile_data["contactPostPassDurationSeconds"]

        message = (
            "The current value of "
            + parameter
            + " duration is "
            + str(value)
            + "s. \n Enter the new value in seconds:"
        )

        duration_question = [
            {
                "type": "input",
                "name": "duration",
                "message": message,
                "validate": DurationValidator,
            }
        ]

        duration_question_answer = prompt(duration_question)
        duration = int(duration_question_answer["duration"])

        if parameter == "minimum contact":
            updated_profile_data["minimumViableContactDurationSeconds"] = duration
        elif parameter == "prepass":
            updated_profile_data["contactPrePassDurationSeconds"] = duration
        elif parameter == "postpass":
            updated_profile_data["contactPostPassDurationSeconds"] = duration

    if parameter == "name":
        name_question = [
            {
                "type": "input",
                "name": "name",
                "message": "Current mission profile name: "
                + str(updated_profile_data["name"])
                + " \n   Enter a new name:",
                "validate": NameValidator,
            }
        ]

        name_question_answer = prompt(name_question)
        name = name_question_answer["name"]

        updated_profile_data["name"] = name

    try:
        response = gs_client.update_mission_profile(
            contactPostPassDurationSeconds=updated_profile_data[
                "contactPostPassDurationSeconds"
            ],
            contactPrePassDurationSeconds=updated_profile_data[
                "contactPrePassDurationSeconds"
            ],
            dataflowEdges=updated_profile_data["dataflowEdges"],
            minimumViableContactDurationSeconds=updated_profile_data[
                "minimumViableContactDurationSeconds"
            ],
            missionProfileId=updated_profile_data["missionProfileId"],
            name=updated_profile_data["name"],
            trackingConfigArn=updated_profile_data["trackingConfigArn"],
        )
    except Exception as e:
        print(e)
    else:
        if (
            parameter == "minimum contact"
            or parameter == "prepass"
            or parameter == "postpass"
        ):
            print(
                "Update complete. The "
                + parameter
                + " duration has been set to: "
                + str(duration)
                + "s."
            )
        if parameter == "name":
            print(
                "Update complete. The mission profile name has been changed to: " + name
            )

    main()


def change_tracking(gs_client, mission_profile_id):
    profile_data = gs_client.get_mission_profile(missionProfileId=mission_profile_id)

    tracking_config_id = profile_data["trackingConfigArn"].split("/")[2]
    tracking_config = gs_client.get_config(
        configId=tracking_config_id, configType="tracking"
    )

    tracking_question = [
        {
            "type": "list",
            "name": "tracking",
            "message": "Currently autotrack is: "
            + str(tracking_config["configData"]["trackingConfig"]["autotrack"])
            + " What new value would you like?",
            "choices": [
                "PREFERRED",
                "REMOVED",
                "REQUIRED",
            ],
        }
    ]

    tracking_answer = prompt(tracking_question)
    tracking = tracking_answer["tracking"]

    try:
        response = gs_client.update_config(
            configData={
                "trackingConfig": {"autotrack": tracking},
            },
            configId=tracking_config["configId"],
            configType="tracking",
            name=tracking_config["name"],
        )
    except Exception as e:
        print(e)
    else:
        print(
            "Update complete. The antenna tracking config has been set to: " + tracking
        )

    main()


def change_uplink_power(gs_client, mission_profile_id):
    uplink_conflig_id = ""

    profile_data = gs_client.get_mission_profile(missionProfileId=mission_profile_id)

    for config_pair in profile_data["dataflowEdges"]:
        for config in config_pair:
            config_id = config.split("/")[2]
            config_type = config.split("/")[1]

            if config_type == "antenna-uplink":
                uplink_conflig_id = config_id
                break

    if not uplink_conflig_id:
        print(
            "There is no antenna uplink config in this mission profile. Exiting to main menu."
        )
        main()

    uplink_config = gs_client.get_config(
        configId=uplink_conflig_id, configType="antenna-uplink"
    )

    current_power = uplink_config["configData"]["antennaUplinkConfig"]["targetEirp"][
        "value"
    ]

    power_question = [
        {
            "type": "input",
            "name": "power",
            "message": "The current EIRP is "
            + str(current_power)
            + "dBW. \n  Enter the desired EIRP. Valid values: 20-50 dBW",
            "validate": PowerValidator,
        }
    ]

    power_question_answer = prompt(power_question)
    power = float(power_question_answer["power"])

    try:
        response = gs_client.update_config(
            configData={
                "antennaUplinkConfig": {
                    "spectrumConfig": {
                        "centerFrequency": {
                            "units": uplink_config["configData"]["antennaUplinkConfig"][
                                "spectrumConfig"
                            ]["centerFrequency"]["units"],
                            "value": uplink_config["configData"]["antennaUplinkConfig"][
                                "spectrumConfig"
                            ]["centerFrequency"]["value"],
                        },
                        "polarization": uplink_config["configData"][
                            "antennaUplinkConfig"
                        ]["spectrumConfig"]["polarization"],
                    },
                    "targetEirp": {"units": "dBW", "value": power},
                    "transmitDisabled": uplink_config["configData"][
                        "antennaUplinkConfig"
                    ]["transmitDisabled"],
                },
            },
            configId=uplink_config["configId"],
            configType=uplink_config["configType"],
            name=uplink_config["name"],
        )
    except Exception as e:
        print(e)
    else:
        print(
            "Update complete. The uplink EIRP has been set to: " + str(power) + "dBW."
        )

    main()


def change_uplink_center_frequency(gs_client, mission_profile_id):
    uplink_conflig_id = ""

    profile_data = gs_client.get_mission_profile(missionProfileId=mission_profile_id)

    for config_pair in profile_data["dataflowEdges"]:
        for config in config_pair:
            config_id = config.split("/")[2]
            config_type = config.split("/")[1]

            if config_type == "antenna-uplink":
                uplink_conflig_id = config_id
                break

    if not uplink_conflig_id:
        print(
            "There is no antenna uplink config in this mission profile. Exiting to main menu."
        )
        main()

    uplink_config = gs_client.get_config(
        configId=uplink_conflig_id, configType="antenna-uplink"
    )

    current_center_frequency = uplink_config["configData"]["antennaUplinkConfig"][
        "spectrumConfig"
    ]["centerFrequency"]["value"]
    center_frequency_unit = uplink_config["configData"]["antennaUplinkConfig"][
        "spectrumConfig"
    ]["centerFrequency"]["units"]

    center_frequency_question = [
        {
            "type": "input",
            "name": "center_frequency",
            "message": "The current uplink center frequency is "
            + str(current_center_frequency)
            + " "
            + str(center_frequency_unit)
            + "\n  Enter the desired uplink center frequency in MHz. You must be licenced for this frequency.",
            "validate": UplinkFrequencyValidator,
        }
    ]

    center_frequency_answer = prompt(center_frequency_question)
    center_frequency = float(center_frequency_answer["center_frequency"])

    try:
        response = gs_client.update_config(
            configData={
                "antennaUplinkConfig": {
                    "spectrumConfig": {
                        "centerFrequency": {
                            "units": "MHz",
                            "value": center_frequency,
                        },
                        "polarization": uplink_config["configData"][
                            "antennaUplinkConfig"
                        ]["spectrumConfig"]["polarization"],
                    },
                    "targetEirp": {
                        "units": uplink_config["configData"]["antennaUplinkConfig"][
                            "targetEirp"
                        ]["units"],
                        "value": uplink_config["configData"]["antennaUplinkConfig"][
                            "targetEirp"
                        ]["value"],
                    },
                    "transmitDisabled": uplink_config["configData"][
                        "antennaUplinkConfig"
                    ]["transmitDisabled"],
                },
            },
            configId=uplink_config["configId"],
            configType=uplink_config["configType"],
            name=uplink_config["name"],
        )
    except Exception as e:
        print(e)
    else:
        print(
            "Update complete. The uplink center frequency has been set to: "
            + str(center_frequency)
            + " MHz."
        )

    main()


def change_downlink_center_frequency(gs_client, mission_profile_id):
    downlink_conflig_id = ""

    profile_data = gs_client.get_mission_profile(missionProfileId=mission_profile_id)

    for config_pair in profile_data["dataflowEdges"]:
        for config in config_pair:
            config_id = config.split("/")[2]
            config_type = config.split("/")[1]

            if config_type == "antenna-downlink":
                downlink_conflig_id = config_id
                break

    if not downlink_conflig_id:
        print(
            "There is no antenna digIf downlink config in this mission profile. Exiting to main menu."
        )
        main()

    downlink_config = gs_client.get_config(
        configId=downlink_conflig_id, configType="antenna-downlink"
    )

    current_center_frequency = downlink_config["configData"]["antennaDownlinkConfig"][
        "spectrumConfig"
    ]["centerFrequency"]["value"]
    center_frequency_unit = downlink_config["configData"]["antennaDownlinkConfig"][
        "spectrumConfig"
    ]["centerFrequency"]["units"]

    center_frequency_question = [
        {
            "type": "input",
            "name": "center_frequency",
            "message": "The current downlink center frequency is "
            + str(current_center_frequency)
            + " "
            + str(center_frequency_unit)
            + "\n  Enter the desired downlink center frequency in MHz. You must be licenced for this frequency.",
            "validate": DownlinkFrequencyValidator,
        }
    ]

    center_frequency_answer = prompt(center_frequency_question)
    center_frequency = float(center_frequency_answer["center_frequency"])

    try:
        response = gs_client.update_config(
            configData={
                "antennaDownlinkConfig": {
                    "spectrumConfig": {
                        "centerFrequency": {
                            "units": "MHz",
                            "value": center_frequency,
                        },
                        "bandwidth": {
                            "units": downlink_config["configData"][
                                "antennaDownlinkConfig"
                            ]["spectrumConfig"]["bandwidth"]["units"],
                            "value": downlink_config["configData"][
                                "antennaDownlinkConfig"
                            ]["spectrumConfig"]["bandwidth"]["value"],
                        },
                        "polarization": downlink_config["configData"][
                            "antennaDownlinkConfig"
                        ]["spectrumConfig"]["polarization"],
                    }
                },
            },
            configId=downlink_config["configId"],
            configType=downlink_config["configType"],
            name=downlink_config["name"],
        )
    except Exception as e:
        print(e)
    else:
        print(
            "Update complete. The downlink center frequency has been set to: "
            + str(center_frequency)
            + " MHz."
        )

    main()


def change_downlink_bandwidth(gs_client, mission_profile_id):
    downlink_conflig_id = ""

    profile_data = gs_client.get_mission_profile(missionProfileId=mission_profile_id)

    for config_pair in profile_data["dataflowEdges"]:
        for config in config_pair:
            config_id = config.split("/")[2]
            config_type = config.split("/")[1]

            if config_type == "antenna-downlink":
                downlink_conflig_id = config_id
                break

    if not downlink_conflig_id:
        print(
            "There is no antenna digIf downlink config in this mission profile. Exiting to main menu."
        )
        main()

    downlink_config = gs_client.get_config(
        configId=downlink_conflig_id, configType="antenna-downlink"
    )

    current_bandwidth = downlink_config["configData"]["antennaDownlinkConfig"][
        "spectrumConfig"
    ]["bandwidth"]["value"]
    bandwidth_unit = downlink_config["configData"]["antennaDownlinkConfig"][
        "spectrumConfig"
    ]["bandwidth"]["units"]

    bandwidth_question = [
        {
            "type": "input",
            "name": "bandwidth",
            "message": "The current downlink bandwidth is "
            + str(current_bandwidth)
            + " "
            + str(bandwidth_unit)
            + "\n  Enter the desired downlink bandwidth in kHz. You must be licenced for this bandwidth.",
            "validate": DownlinkBandwidthValidator,
        }
    ]

    bandwidth_answer = prompt(bandwidth_question)
    bandwidth = float(bandwidth_answer["bandwidth"])

    try:
        response = gs_client.update_config(
            configData={
                "antennaDownlinkConfig": {
                    "spectrumConfig": {
                        "centerFrequency": {
                            "units": downlink_config["configData"][
                                "antennaDownlinkConfig"
                            ]["spectrumConfig"]["centerFrequency"]["units"],
                            "value": downlink_config["configData"][
                                "antennaDownlinkConfig"
                            ]["spectrumConfig"]["centerFrequency"]["value"],
                        },
                        "bandwidth": {
                            "units": "kHz",
                            "value": bandwidth,
                        },
                        "polarization": downlink_config["configData"][
                            "antennaDownlinkConfig"
                        ]["spectrumConfig"]["polarization"],
                    }
                },
            },
            configId=downlink_config["configId"],
            configType=downlink_config["configType"],
            name=downlink_config["name"],
        )
    except Exception as e:
        print(e)
    else:
        print(
            "Update complete. The downlink bandwidth frequency has been set to: "
            + str(bandwidth)
            + " kHz."
        )

    main()


class DurationValidator(Validator):
    def validate(self, document):
        ok = regex.match("^([1-9]|[1-9][0-9]|[1-2][0-9][0-9]|^300)$", document.text)
        if not ok:
            raise ValidationError(
                message="Please enter a valid duration value in seconds [1-300]",
                cursor_position=len(document.text),
            )


class NameValidator(Validator):
    def validate(self, document):
        ok = regex.match("^[a-zA-Z0-9-\s\d]*$", document.text)
        if not ok:
            raise ValidationError(
                message="Please enter a valid name. Allowed characters: a-z, A-Z, 0-9, -, and space",
                cursor_position=len(document.text),
            )


class PowerValidator(Validator):
    def validate(self, document):
        ok = regex.match("^[2-4][0-9]?$|^50$", document.text)
        if not ok:
            raise ValidationError(
                message="Please enter a valid EIRP dBw value [20-50]",
                cursor_position=len(document.text),
            )


class UplinkFrequencyValidator(Validator):
    def validate(self, document):
        ok = regex.match("^202[5-9]|20[3-9][0-9]|21[0-1][0-9]?$|^2120$", document.text)
        if not ok:
            raise ValidationError(
                message="This uplink center frequency is not supported. Valid values are between 2025 to 2120 MHz, for which you are licenced.",
                cursor_position=len(document.text),
            )


class DownlinkFrequencyValidator(Validator):
    def validate(self, document):
        ok = regex.match(
            "^22[0-9][0-9]?$|^2300|77[5-9][0-9]|7[8-9][0-9][0-9]|8[0-3][0-9][0-9]|^8400$",
            document.text,
        )
        if not ok:
            raise ValidationError(
                message="This downlink center frequency is not supported. Valid values are between 2200 to 2300 MHz and 7750 to 8400 MHz, for which you are licenced.",
                cursor_position=len(document.text),
            )


class DownlinkBandwidthValidator(Validator):
    def validate(self, document):
        ok = regex.match(
            "^[1-9][0-9]$|^[1-9][0-9][0-9]?$|^[1-9][0-9][0-9][0-9]?$|^[1-3][0-9][0-9][0-9][0-9]?$|^40000$",
            document.text,
        )
        if not ok:
            raise ValidationError(
                message="This downlink bandwidth is not supported. Valid values are between 10 and 40000 kHz, for which you are licenced.",
                cursor_position=len(document.text),
            )


def main():

    task_question = [
        {
            "type": "list",
            "name": "task",
            "message": "What would you like to do?",
            "choices": [
                "View mission profile",
                "Update mission profile",
                "Quit",
            ],
        }
    ]

    task_answer = prompt(task_question)
    task = task_answer["task"]

    if task == "Quit":
        quit()

    region_question = [
        {
            "type": "list",
            "name": "region",
            "message": "Which region would you like to use?",
            "choices": [
                "N. Virginia (us-east-1)",
                "Ohio (us-east-2)",
                "Oregon (us-west-2)",
                "Cape Town (af-south-1)",
                "Seoul (ap-northest-2)",
                "Sydney (ap-south-east-2)",
                "Frankfurt (eu-central-1)",
                "Ireland (eu-west-1)",
                "Stockholm (eu-north-1)",
                "Bahrain (me-south-1)",
                "Sao Paulo (sa-east-1)",
            ],
        }
    ]

    answer = prompt(region_question)
    full_region = answer["region"]

    region = full_region[full_region.find("(") + 1 : full_region.find(")")]

    my_config = Config(
        region_name=region,
        signature_version="v4",
        retries={"max_attempts": 4, "mode": "standard"},
    )

    gs_client = boto3.client("groundstation", config=my_config)

    try:
        mission_profile_list = gs_client.list_mission_profiles()
    except Exception as e:
        print(
            "Your AWS account doesn't have access to this region. Exiting to main menu."
        )
        print(e)
        main()

    if not mission_profile_list["missionProfileList"]:
        print("No mission profiles in " + full_region + ". Exiting to main menu.")
        main()

    profile_question = [
        {
            "type": "list",
            "name": "mission_profile_name",
            "message": "Which mission profile would you like to view?",
            "choices": get_mission_profile_list(gs_client),
        }
    ]

    profile_answer = prompt(profile_question)["mission_profile_name"]
    if profile_answer == "Exit":
        print("No mission profile selected. Exiting to main menu.")
        main()
    mission_profile_name = profile_answer.split("--")[0].strip()
    mission_profile_id = profile_answer.split("--")[1].strip()

    if task == "View mission profile":
        view_mission_profile(gs_client, mission_profile_id, mission_profile_name)
    elif task == "Update mission profile":
        update_mission_profile(gs_client, mission_profile_id)


if __name__ == "__main__":
    main()
