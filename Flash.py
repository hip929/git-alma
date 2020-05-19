import os
from testlogger import logger
import automationresultcode as arc
import testautomationextras as tae

from DoloresTools.Dolores import Dolores, IMAGES, IMAGE_MAP, getHistoricCommandsPath
from DoloresTools.SetupTest import setup
from DoloresTools.Download import (
	formatBuildNumber,
	getBuildPath,
	getDarwinPath,
	DEFAULT_DOWNLOAD_PATH,
)
from DoloresTools.Update import update, UpdateCode
from DoloresTools.AgentResources import update as updateProperties
from DoloresTools.Scripts.QFCTReport import BUILD_INFO_PATH

tae.meta_data(
	Category="Update",
	ID=os.path.splitext(os.path.basename(__file__))[0],
	Type=os.path.basename(__file__),
	Timeout=1800,
	Arguments={},
	RequiredResources=[{"Type": ["B380", "Raider"], "Label": "DUT"}],
	Description="Flash Dolores devices",
	Maintainer=dict(
		Name="Neha Gondkar",
		Email="ngondkar@apple.com",
		ODGroupname="Beats Tools Development",
	),
)


def flash(context):
	device = context.resources[0]
	name = device.properties["name"]
	trigger = context.test.get("BuildTrigger")
	triggerType = context.test.get("trigger_type")
	imageName = context.arguments.get("image", None)
	forceFlash = context.arguments.get("forceFlash", False)
	abortIfOnBuild = context.arguments.get("abortIfOnBuild", False)
	branch = context.arguments.get("branch", "Dolores-Ubuntu")
	attempts = context.arguments.get("attempts", 3)
	image = imageName if (imageName is not None) and imageName in IMAGES else "development"
	downloadPath = DEFAULT_DOWNLOAD_PATH
	log = os.path.join(context.logFolder, "flash.log")

	if trigger:
		logger.info(f"Trigger has type {triggerType}")
		if triggerType == "cron":
			build = context.arguments.get("build", "latest")
		else:
			build = trigger.get("build", "latest")
	else:
		build = context.arguments.get("build", "latest")

	logger.info(f"Build requested {build}")
	buildNumber, _, _ = formatBuildNumber(build, branch=branch)
	# NOTE: this tracks the last attempted build on the local machine
	with open(BUILD_INFO_PATH, "w") as fd:
		fd.write("{}{}".format(IMAGE_MAP[image], buildNumber))

	if not forceFlash:
		buildPath = getBuildPath(branch, buildNumber, downloadPath)
		adbDarwinPath = getDarwinPath(buildPath)
		if os.path.exists(adbDarwinPath):
			with Dolores(adbDarwinPath=adbDarwinPath) as deviceInstance:
				imageType, deviceVersion = deviceInstance.versionInfo()
			if (
				(buildNumber == deviceVersion)
				and (imageType == image)
				and (device.properties.get("branch") == branch)
			):
				if abortIfOnBuild:
					# NOTE: no need to send report
					with open(BUILD_INFO_PATH, "w") as fd:
						fd.write("abort")
					context.close(arc.ARC410(), "DUT was already on the build. Aborting")
				else:
					context.close(arc.ARC202(), "DUT was already on the build")

	logger.info(
		f'Flashing build: {buildNumber} from branch "{branch}"" with "{image}" image'
	)
	with open(log, "w") as f:
		for attempt in range(attempts):
			result, version = update(
				build, branch=branch, image=image, destination=downloadPath, log=f
			)
			if result == UpdateCode.Success:
				break
			else:
				logger.warning(
					f"Flash failed on attempt: {attempt + 1} with reason: {result}. Retrying..."
				)

	if result != UpdateCode.Success:
		logger.warning(f"Flash failed after multiple attempts: {result}")
		context.close(arc.ARC400(), "Device did not update successfully")
	elif not version:
		logger.warning("Device updated but failed to get device build after update")
		context.close(arc.ARC400(), "Device updated but failed to get build")
	else:
		logger.info("Flash success")
		logger.info(f"Device build after update {version}")

		# NOTE: Flashing, so clear historic commands
		historicCommandsPath = getHistoricCommandsPath(device.properties["serialNumber"])
		with open(historicCommandsPath, "w"):
			pass

		device.properties["branch"] = branch
		device.properties["device_build"] = version
		device.properties["build"] = version
		properties = {
			key: value for key, value in device.properties.items() if key != "object"
		}
		for key, value in properties.items():
			updateProperties(name, key, value)
	context.close(arc.ARC200())


if __name__ == "__main__":
	with setup(kwargs={0: {"setupName": False}}) as context:
		flash(context)
