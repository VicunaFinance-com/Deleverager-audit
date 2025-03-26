init-hooks: 
	pre-commit install -c .tool_configurations/.pre-commit-config.yaml --install-hooks --overwrite
format-contracts:
	prettier --write '*/contracts/**/*.sol' -c .prettierrc.yaml
format-interfaces:
	prettier --write '*/interfaces/**/*.sol'
isort:
	isort --settings-file .tool_configurations/isort.cfg .

launch-anvil:
	anvil --fork-url https://rpc.soniclabs.com --auto-impersonate --base-fee 0 --steps-tracing

black:
	black .
# autopep8:
# 	autopep8 -j 0 --in-place --global-config .tool_configurations/autopep8 --ignore-local-config .

format-python: isort black

format-all: format-contracts format-python

add-sonic-main:
	brownie networks add Sonic sonic-main host=https://rpc.soniclabs.com chainid=146 explorer=https://api.sonicscan.org/api
add-sonic-fork:
	brownie networks add Sonic sonic-fork host=http://127.0.0.1:8545 chainid=146 explorer=https://api.sonicscan.org/api
