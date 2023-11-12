#!/bin/python3
import argparse
import os
import sys
from pathlib import Path
from typing import Literal


EPP_STATE_DEFAULT = "default"
EPP_STATE_PERFORMANCE = "performance"
EPP_STATE_BALANCE_PERFORMANCE = "balance_performance"
EPP_STATE_BALANCE_POWER = "balance_power"
EPP_STATE_POWER = "power"

EPP_STATE_LIST = [
    EPP_STATE_DEFAULT,
    EPP_STATE_PERFORMANCE,
    EPP_STATE_BALANCE_PERFORMANCE,
    EPP_STATE_BALANCE_POWER,
    EPP_STATE_POWER,
]


TypeEppState = Literal[
    "default",
    "performance",
    "balance_performance",
    "balance_power",
    "power",
]


def std_err(s: str) -> str:
    return f"\033[91m{s}\033[0m"


def std_warn(s: str) -> str:
    return f"\033[93m{s}\033[0m"


def std_info(s: str) -> str:
    return f"\033[1m{s}\033[0m"


def check_root() -> None:
    if os.geteuid() == 0:
        return
    print("amd_epp_power_save must be run with root privileges.")
    sys.stdout.flush()
    exit(1)


def check_driver() -> None:
    scaling_driver_path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_driver"
    try:
        with open(scaling_driver_path) as f:
            scaling_driver = f.read()[:-1]
    except FileNotFoundError:
        scaling_driver = None
    if scaling_driver == "amd-pstate-epp":
        return
    print("The system is not running amd-pstate-epp driver.")
    sys.stdout.flush()
    exit(1)


def check_charging() -> bool:
    power_supply_path = Path("/sys/class/power_supply/")
    power_supplies = power_supply_path.glob("*")
    # sort it so AC is 'always' first
    power_supplies = sorted(power_supplies)
    if not power_supplies == 0:
        return True

    for supply in power_supplies:
        supply_type_path = power_supply_path / supply / "type"
        supply_online_path = power_supply_path / supply / "online"
        supply_status_path = power_supply_path / supply / "status"

        if not supply_type_path.exists():
            continue

        with supply_type_path.open() as f:
            supply_type = f.read()[:-1]

        if supply_type == "Mains":
            if not supply_online_path.exists():
                continue
            with supply_online_path.open() as f:
                val = int(f.read()[:-1])
            if val == 1:
                return True

        elif supply_type == "Battery":
            if not supply_status_path.exists():
                continue
            with supply_status_path.open() as f:
                val = int(f.read()[:-1])
            if val == "Discharging":
                return False

    # assume AC power by default
    return True


def set_governor():
    governor_file_path = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    if not governor_file_path.exists():
        sys.stdout.write(
            std_info(
                f"Could not find {governor_file_path} file. Skipping governor setting."
            )
        )
        sys.stdout.flush()
        return

    with governor_file_path.open() as gov_file:
        cur_governor = gov_file.read()[:-1]
    if cur_governor == "powersave":
        return

    sys.stdout.write(std_warn('Setting cpufreq governor to "powersave"'))
    sys.stdout.flush()

    for cpu in range(os.cpu_count()):
        governor_file_path = Path(
            f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor"
        )
        if not governor_file_path.exists():
            continue
        with governor_file_path.open("w") as f:
            f.write("powersave\n")


def set_epp(epp_state_value: TypeEppState):
    if not check_charging() and epp_state_value in [
        EPP_STATE_PERFORMANCE,
        EPP_STATE_BALANCE_PERFORMANCE,
    ]:
        sys.stdout.write(
            std_warn(
                "It seems system is not running on AC power right now, setting performance epp state might not be optimal."
            )
        )
        sys.stdout.flush()

    set_governor()

    for cpu in range(os.cpu_count()):
        epp_file_path = Path(
            f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/energy_performance_preference"
        )
        if not epp_file_path.exists():
            continue
        sys.stdout.write(
            std_info(f"Setting epp_state to {epp_state_value} for cpu{cpu}\n")
        )
        with epp_file_path.open("w") as f:
            f.write(f"{epp_state_value}\n")


if __name__ == "__main__":
    check_root()
    check_driver()
    parser = argparse.ArgumentParser(
        prog="Python script to set energy performance preferences (EPP) of your AMD CPU using the AMD-Pstate driver."
    )
    parser.add_argument(
        "epp_state_value",
        nargs="?",
        help="epp_state value to set",
        choices=EPP_STATE_LIST,
    )
    args = parser.parse_args()

    if not args.epp_state_value:
        choices = ", ".join(EPP_STATE_LIST)
        sys.stdout.write(
            f"{std_err('No epp_state value provided. Provide one of the options from this list: ')}{std_info(f'{choices}')}"
        )
        sys.exit(-1)

    set_epp(args.epp_state_value)
