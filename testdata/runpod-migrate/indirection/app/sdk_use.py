import runpod
runpod.api_key = "x"
pod = runpod.create_pod("trainer", "org/img:tag", "NVIDIA RTX A5000")
