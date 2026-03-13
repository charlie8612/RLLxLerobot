#!/usr/bin/env python3
"""
Eval script with manual success/fail annotation.

Wraps LeRobot's record_loop() to run policy eval episodes one at a time,
prompting the operator to mark each episode as success (s) or fail (f).
Results are saved to a CSV log and optionally uploaded to wandb.

Does NOT modify LeRobot source code.

Usage:
    conda activate piper
    cd ~/piper-lerobot
    python scripts/5_eval_diffusion_custom.py

Config: edit the constants below.
"""

import csv
import logging
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

# ===========================
#  Config — 改這裡就好
# ===========================

# Policy checkpoint (pretrained_model dir)
POLICY_PATH = "/tmp2/charlie/training-outputs/diffusion_dual_cam/checkpoints/last/pretrained_model"

# Robot
CAN_PORT = "piper_left"
TELEOP_PORT = "/dev/robotis_left"
CAMERAS = {
    "overhead": {"index_or_path": "/dev/cam_c270", "width": 640, "height": 480, "fps": 30},
    "wrist":    {"index_or_path": "/dev/cam_arc", "width": 640, "height": 480, "fps": 30},
}

# Eval
NUM_EPISODES = 5
EPISODE_TIME_S = 20       # seconds per eval episode
RESET_TIME_S = 5          # seconds for manual reset between episodes
TASK = "pick up cube"
FPS = 20

# Dataset (eval recordings are saved here)
EVAL_REPO_ID = "charliechan/eval_diffusion_dual_cam"
DATASET_ROOT = Path("/home/charliechan/dataset")

# Display
DISPLAY_DATA = True       # show Rerun GUI

# Wandb (optional — set to None to skip)
WANDB_PROJECT = "piper-pick-cube"  # same project as training
# Run name & group auto-derived from POLICY_PATH:
#   e.g. "outputs/train/diffusion_dual_cam/checkpoints/last/pretrained_model"
#   → group: "diffusion_dual_cam", run_name: "eval_diffusion_dual_cam_last"
_policy_parts = Path(POLICY_PATH).parts
_train_name = _policy_parts[_policy_parts.index("train") + 1] if "train" in _policy_parts else "unknown"
_ckpt_name = _policy_parts[_policy_parts.index("checkpoints") + 1] if "checkpoints" in _policy_parts else "unknown"
WANDB_GROUP = _train_name                                    # groups eval with its training run
WANDB_RUN_NAME = f"eval_{_train_name}_{_ckpt_name}"          # e.g. eval_diffusion_dual_cam_last

# Output
EVAL_LOG_DIR = Path("/tmp2/charlie/training-outputs/eval")

# Safe shutdown — rest position (from tools/waypoint.py)
SAFE_SPEED = 30.0     # deg/s
MIN_DURATION = 0.3
CONTROL_RATE = 100.0
REST_STATE = {
    "joint_1.pos": -0.83,
    "joint_2.pos": -0.14,
    "joint_3.pos": -0.38,
    "joint_4.pos": -1.39,
    "joint_5.pos": 0.0,
    "joint_6.pos": 2.11,
    "gripper.pos": 0.0,
}


# ===========================
#  Main
# ===========================

JOINT_KEYS = [f"joint_{i}.pos" for i in range(1, 7)]
GRIPPER_KEY = "gripper.pos"
ALL_KEYS = JOINT_KEYS + [GRIPPER_KEY]


def safe_disconnect(robot):
    """Move to rest position before disconnecting to prevent the arm from dropping."""
    print("\n  Moving to rest position...")
    try:
        obs = robot.get_observation()
        current = {k: obs[k] for k in ALL_KEYS}
        # Compute duration based on max joint displacement
        max_delta = max(abs(REST_STATE[k] - current[k]) for k in ALL_KEYS)
        duration = max(max_delta / SAFE_SPEED, MIN_DURATION)
        # Smoothstep interpolation to rest
        steps = max(int(duration * CONTROL_RATE), 1)
        dt = 1.0 / CONTROL_RATE
        for i in range(steps):
            t = (i + 1) / steps
            t = t * t * (3 - 2 * t)  # smoothstep
            action = {k: current[k] + t * (REST_STATE[k] - current[k]) for k in ALL_KEYS}
            robot.send_action(action)
            time.sleep(dt)
        print("  Rest position reached.")
    except Exception as e:
        print(f"  Warning: failed to reach rest position: {e}")
    robot.disconnect()


def prompt_success() -> str:
    """Prompt operator for success/fail. Returns 's' or 'f'."""
    while True:
        try:
            key = input("\n  Episode result — [s]uccess / [f]ail / [d]iscard: ").strip().lower()
        except EOFError:
            return "f"
        if key in ("s", "f", "d"):
            return key
        print("  Please press s, f, or d.")


def main():
    # Lazy imports so --help is fast
    from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    from lerobot.datasets.pipeline_features import (
        aggregate_pipeline_dataset_features,
        create_initial_features,
    )
    from lerobot.datasets.utils import combine_feature_dicts
    from lerobot.datasets.video_utils import VideoEncodingManager
    from lerobot.policies.factory import make_policy, make_pre_post_processors
    from lerobot.processor import make_default_processors
    from lerobot.processor.rename_processor import rename_stats
    from lerobot.robots import make_robot_from_config
    from lerobot.scripts.lerobot_record import record_loop
    from lerobot.teleoperators import make_teleoperator_from_config
    from lerobot.utils.control_utils import init_keyboard_listener
    from lerobot.utils.import_utils import register_third_party_plugins
    from lerobot.utils.utils import init_logging, log_say
    from lerobot.utils.visualization_utils import init_rerun

    register_third_party_plugins()
    init_logging()

    import os
    display_data = DISPLAY_DATA
    if display_data and os.environ.get("DISPLAY"):
        init_rerun(session_name="eval")
    elif display_data:
        logging.warning("No DISPLAY set (SSH?). Skipping Rerun GUI. Run from desktop terminal for display.")
        display_data = False

    # --- Build robot & teleop configs ---
    from lerobot_robot_piper.config_piper_follower import PiperFollowerConfig
    from lerobot_teleoperator_robotis.config_robotis_leader import RobotisLeaderConfig

    robot_cfg = PiperFollowerConfig(
        can_port=CAN_PORT,
        speed_rate=20,
        max_relative_target=5.0,  # max 5 degrees per step to prevent jerky moves
        cameras={
            name: OpenCVCameraConfig(
                index_or_path=cam["index_or_path"],
                width=cam["width"],
                height=cam["height"],
                fps=cam["fps"],
            )
            for name, cam in CAMERAS.items()
        },
    )
    teleop_cfg = RobotisLeaderConfig(port=TELEOP_PORT)

    robot = make_robot_from_config(robot_cfg)
    teleop = make_teleoperator_from_config(teleop_cfg)

    teleop_action_processor, robot_action_processor, robot_observation_processor = (
        make_default_processors()
    )

    # --- Dataset features ---
    dataset_features = combine_feature_dicts(
        aggregate_pipeline_dataset_features(
            pipeline=teleop_action_processor,
            initial_features=create_initial_features(action=robot.action_features),
            use_videos=True,
        ),
        aggregate_pipeline_dataset_features(
            pipeline=robot_observation_processor,
            initial_features=create_initial_features(observation=robot.observation_features),
            use_videos=True,
        ),
    )

    # --- Dataset (resume if already exists) ---
    from lerobot.utils.utils import get_safe_torch_device
    dataset_root = DATASET_ROOT / EVAL_REPO_ID
    if dataset_root.exists():
        logging.info(f"Resuming existing eval dataset: {EVAL_REPO_ID}")
        dataset = LeRobotDataset(EVAL_REPO_ID, root=dataset_root)
    else:
        dataset = LeRobotDataset.create(
            EVAL_REPO_ID,
            FPS,
            root=dataset_root,
            robot_type=robot.name,
            features=dataset_features,
            use_videos=True,
        )

    # --- Policy ---
    from lerobot.configs.policies import PreTrainedConfig

    policy_cfg = PreTrainedConfig.from_pretrained(POLICY_PATH)
    policy_cfg.pretrained_path = POLICY_PATH
    policy = make_policy(policy_cfg, ds_meta=dataset.meta)
    preprocessor, postprocessor = make_pre_post_processors(
        policy_cfg=policy_cfg,
        pretrained_path=POLICY_PATH,
        dataset_stats=rename_stats(dataset.meta.stats, {}),
        preprocessor_overrides={
            "device_processor": {"device": policy_cfg.device},
            "rename_observations_processor": {"rename_map": {}},
        },
    )

    # --- Eval log setup ---
    EVAL_LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = EVAL_LOG_DIR / f"eval_{timestamp}.csv"
    csv_file = open(csv_path, "w", newline="")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["episode", "result", "policy_path", "task", "timestamp"])

    results = []  # list of 's' or 'f'

    # --- Warmup: run one dummy inference to compile CUDA kernels ---
    print("[warmup] Running dummy inference to compile CUDA kernels...")
    import torch
    device = get_safe_torch_device(policy_cfg.device)
    dummy_obs = {}
    for key, feat in policy_cfg.input_features.items():
        shape = [1] + list(feat.shape)  # add batch dim
        if feat.type.name == "VISUAL":
            dummy_obs[key] = torch.rand(shape, dtype=torch.float32, device=device)
        else:
            dummy_obs[key] = torch.zeros(shape, dtype=torch.float32, device=device)
    with torch.inference_mode():
        preprocessed = preprocessor(dummy_obs)
        _ = policy.select_action(preprocessed)
    policy.reset()
    print("[warmup] Done.")

    # --- Connect hardware ---
    robot.connect()
    teleop.connect()
    listener, events = init_keyboard_listener()

    # --- SIGINT handler: graceful stop ---
    def handle_sigint(sig, frame):
        events["stop_recording"] = True
        events["exit_early"] = True
        print("\n\nInterrupted -- finishing up safely...")

    signal.signal(signal.SIGINT, handle_sigint)

    try:
        with VideoEncodingManager(dataset):
            recorded = 0
            while recorded < NUM_EPISODES and not events["stop_recording"]:
                ep_num = dataset.num_episodes
                print(f"\n{'='*50}")
                print(f"  Episode {recorded + 1}/{NUM_EPISODES}  (dataset ep {ep_num})")
                print(f"{'='*50}")
                log_say(f"Recording episode {ep_num}", play_sounds=True)

                # --- Run one eval episode ---
                record_loop(
                    robot=robot,
                    events=events,
                    fps=FPS,
                    teleop_action_processor=teleop_action_processor,
                    robot_action_processor=robot_action_processor,
                    robot_observation_processor=robot_observation_processor,
                    teleop=teleop,
                    policy=policy,
                    preprocessor=preprocessor,
                    postprocessor=postprocessor,
                    dataset=dataset,
                    control_time_s=EPISODE_TIME_S,
                    single_task=TASK,
                    display_data=display_data,
                )

                # --- Prompt for result ---
                result = prompt_success()

                if result == "d":
                    print("  -> Discarded. Clearing episode buffer.")
                    dataset.clear_episode_buffer()
                    events["exit_early"] = False
                    # Still do reset
                    if not events["stop_recording"] and recorded < NUM_EPISODES - 1:
                        log_say("Reset the environment", play_sounds=True)
                        record_loop(
                            robot=robot,
                            events=events,
                            fps=FPS,
                            teleop_action_processor=teleop_action_processor,
                            robot_action_processor=robot_action_processor,
                            robot_observation_processor=robot_observation_processor,
                            teleop=teleop,
                            control_time_s=RESET_TIME_S,
                            single_task=TASK,
                            display_data=display_data,
                        )
                    continue

                label = "SUCCESS" if result == "s" else "FAIL"
                print(f"  -> {label}")
                results.append(result)

                # Write CSV row
                csv_writer.writerow([
                    ep_num, result, POLICY_PATH, TASK,
                    datetime.now().isoformat(),
                ])
                csv_file.flush()

                # --- Reset period ---
                if not events["stop_recording"] and recorded < NUM_EPISODES - 1:
                    log_say("Reset the environment", play_sounds=True)
                    record_loop(
                        robot=robot,
                        events=events,
                        fps=FPS,
                        teleop_action_processor=teleop_action_processor,
                        robot_action_processor=robot_action_processor,
                        robot_observation_processor=robot_observation_processor,
                        teleop=teleop,
                        control_time_s=RESET_TIME_S,
                        single_task=TASK,
                        display_data=display_data,
                    )

                if events["rerecord_episode"]:
                    events["rerecord_episode"] = False
                    events["exit_early"] = False
                    dataset.clear_episode_buffer()
                    results.pop()  # remove last result
                    continue

                dataset.save_episode()
                recorded += 1

    finally:
        print("[cleanup] log_say stop recording...")
        log_say("Stop recording", play_sounds=False)

        print("[cleanup] dataset.finalize()...")
        if dataset:
            dataset.finalize()
        print("[cleanup] safe_disconnect(robot)...")
        if robot.is_connected:
            safe_disconnect(robot)
        print("[cleanup] teleop.disconnect()...")
        if teleop.is_connected:
            teleop.disconnect()
        print("[cleanup] listener.stop()...")
        if listener:
            listener.stop()

        csv_file.close()
        print("[cleanup] done.")

    # --- Summary ---
    n_success = results.count("s")
    n_fail = results.count("f")
    n_total = len(results)
    success_rate = n_success / n_total if n_total > 0 else 0.0

    print(f"\n{'='*50}")
    print(f"  EVAL SUMMARY")
    print(f"  Policy: {POLICY_PATH}")
    print(f"  Task:   {TASK}")
    print(f"  Total:  {n_total}  |  Success: {n_success}  |  Fail: {n_fail}")
    print(f"  Success Rate: {success_rate:.1%}")
    print(f"  Log: {csv_path}")
    print(f"{'='*50}\n")

    # --- Wandb (optional) ---
    if WANDB_PROJECT:
        try:
            import wandb

            print("[wandb] init...")
            run_name = f"{WANDB_RUN_NAME}_{timestamp}"
            wandb.init(
                project=WANDB_PROJECT,
                name=run_name,
                group=WANDB_GROUP,
                job_type="eval",
                config={
                    "policy_path": POLICY_PATH,
                    "checkpoint": _ckpt_name,
                    "task": TASK,
                    "num_episodes": n_total,
                    "episode_time_s": EPISODE_TIME_S,
                    "fps": FPS,
                },
            )
            print("[wandb] logging metrics...")
            wandb.log({
                "eval/success_rate": success_rate,
                "eval/num_success": n_success,
                "eval/num_fail": n_fail,
                "eval/num_total": n_total,
            })
            print("[wandb] finishing (timeout=30)...")
            wandb.finish()
            print(f"  Wandb: logged to project '{WANDB_PROJECT}', run '{run_name}'")
        except Exception as e:
            print(f"  Wandb upload failed: {e}")


if __name__ == "__main__":
    main()
