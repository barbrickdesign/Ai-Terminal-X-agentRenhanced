#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# === Micro Terminal Manager ===
# Manages lightweight micro terminal sessions that can be deployed
# alongside virtual machines (local, Docker containers, or SSH hosts).

import os
import shlex
import shutil
import subprocess
import sys

# Colors (matching main script)
red = "\033[91m"; green = "\033[32m"; blue = "\033[94m"; purple = "\033[95m"
gold = "\033[38;5;220m"; cyan = "\033[36m"; yellow = "\033[93m"; reset = "\033[0m"

# Prefix applied to all micro terminal tmux session names so they can be
# distinguished from the main viewer session.
MICRO_TERM_PREFIX = "aitx-micro-"

# Supported VM types for micro terminal deployment.
VM_TYPES = ("local", "docker", "ssh")


def _get_tmux_path():
    """Returns the path to tmux, or None if not found."""
    return shutil.which("tmux")


def _get_docker_path():
    """Returns the path to docker, or None if not found."""
    return shutil.which("docker")


def _get_ssh_path():
    """Returns the path to the ssh client, or None if not found."""
    return shutil.which("ssh")


def _session_exists(tmux_path, session_name):
    """Returns True if the given tmux session is currently running."""
    try:
        result = subprocess.run(
            [tmux_path, "has-session", "-t", session_name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3
        )
        return result.returncode == 0
    except Exception:
        return False


def list_micro_terminals():
    """
    Returns a list of active micro terminal session names (stripped of prefix).
    Returns an empty list if none exist or tmux is unavailable.
    """
    tmux = _get_tmux_path()
    if not tmux:
        return []
    try:
        result = subprocess.run(
            [tmux, "list-sessions", "-F", "#{session_name}"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return []
        return [
            s[len(MICRO_TERM_PREFIX):]
            for s in result.stdout.strip().splitlines()
            if s.startswith(MICRO_TERM_PREFIX)
        ]
    except Exception:
        return []


def create_micro_terminal(name, vm_type="local", vm_target=None):
    """
    Creates a new named micro terminal (detached tmux session).

    Args:
        name      : Short identifier for this terminal.
        vm_type   : "local" (default), "docker" (exec into container), or
                    "ssh" (connect to remote host).
        vm_target : Required for docker/ssh.
                    docker -> container name or ID
                    ssh    -> user@host string

    Returns:
        (success: bool, session_name: str | None, message: str)
    """
    tmux = _get_tmux_path()
    if not tmux:
        return False, None, "tmux is not installed or not found in PATH."

    if vm_type not in VM_TYPES:
        return False, None, f"Unknown vm_type '{vm_type}'. Choose from: {', '.join(VM_TYPES)}."

    session_name = f"{MICRO_TERM_PREFIX}{name}"

    if _session_exists(tmux, session_name):
        return False, session_name, f"Micro terminal '{name}' already exists."

    # Build the shell command that will run inside the new tmux session.
    if vm_type == "docker":
        if not vm_target:
            return False, None, "docker vm_type requires a container name/ID (vm_target)."
        docker = _get_docker_path()
        if not docker:
            return False, None, "Docker is not installed or not found in PATH."
        # Prefer bash inside the container, fall back to sh.
        start_cmd = (
            f"{docker} exec -it {vm_target} "
            f"/bin/sh -c 'command -v bash >/dev/null 2>&1 && exec bash || exec sh'"
        )

    elif vm_type == "ssh":
        if not vm_target:
            return False, None, "ssh vm_type requires a user@host target (vm_target)."
        ssh = _get_ssh_path()
        if not ssh:
            return False, None, "SSH client is not installed or not found in PATH."
        start_cmd = f"{ssh} {vm_target}"

    else:  # local
        start_cmd = os.environ.get("SHELL", "/bin/bash")

    try:
        subprocess.run(
            [tmux, "new-session", "-d", "-s", session_name, start_cmd],
            check=True, capture_output=True, text=True, timeout=10
        )
        return True, session_name, f"Micro terminal '{name}' created successfully."
    except subprocess.CalledProcessError as e:
        err = e.stderr.strip() if e.stderr else str(e)
        return False, None, f"Failed to create micro terminal: {err}"
    except Exception as e:
        return False, None, f"Unexpected error creating micro terminal: {e}"


def destroy_micro_terminal(name):
    """
    Destroys an existing micro terminal session.

    Returns:
        (success: bool, message: str)
    """
    tmux = _get_tmux_path()
    if not tmux:
        return False, "tmux is not installed or not found in PATH."

    session_name = f"{MICRO_TERM_PREFIX}{name}"
    try:
        subprocess.run(
            [tmux, "kill-session", "-t", session_name],
            check=True, capture_output=True, text=True, timeout=5
        )
        return True, f"Micro terminal '{name}' destroyed."
    except subprocess.CalledProcessError as e:
        err = e.stderr.strip() if e.stderr else str(e)
        if "session not found" in err.lower() or "no server running" in err.lower():
            return False, f"Micro terminal '{name}' not found."
        return False, f"Failed to destroy micro terminal: {err}"
    except Exception as e:
        return False, f"Unexpected error destroying micro terminal: {e}"


def send_to_micro_terminal(name, command):
    """
    Sends a command string to a running micro terminal session.

    Returns:
        (success: bool, message: str)
    """
    tmux = _get_tmux_path()
    if not tmux:
        return False, "tmux is not installed or not found in PATH."

    session_name = f"{MICRO_TERM_PREFIX}{name}"
    try:
        subprocess.run(
            [tmux, "send-keys", "-t", f"{session_name}:0.0", command, "C-m"],
            check=True, capture_output=True, text=True, timeout=5
        )
        return True, f"Command sent to micro terminal '{name}'."
    except subprocess.CalledProcessError as e:
        err = e.stderr.strip() if e.stderr else str(e)
        if "session not found" in err.lower() or "no server running" in err.lower():
            return False, f"Micro terminal '{name}' not found or has been closed."
        return False, f"Failed to send command: {err}"
    except Exception as e:
        return False, f"Unexpected error sending command: {e}"


def attach_micro_terminal(name, visual_terminal_path):
    """
    Opens the micro terminal in the visual terminal application by attaching
    to the tmux session.

    Returns:
        (success: bool, message: str)
    """
    tmux = _get_tmux_path()
    if not tmux:
        return False, "tmux is not installed or not found in PATH."
    if not visual_terminal_path:
        return False, "No visual terminal application path provided."

    session_name = f"{MICRO_TERM_PREFIX}{name}"
    if not _session_exists(tmux, session_name):
        return False, f"Micro terminal '{name}' not found."

    tmux_cmd = f"{shlex.quote(tmux)} attach-session -t {shlex.quote(session_name)}"
    term_args = [
        visual_terminal_path,
        "-T", f"Micro Terminal: {name}",
        "-e", f'bash -c "{tmux_cmd}"',
    ]
    try:
        subprocess.Popen(term_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, f"Opened micro terminal '{name}' in a new window."
    except FileNotFoundError:
        return False, f"Visual terminal '{visual_terminal_path}' not found."
    except Exception as e:
        return False, f"Failed to open micro terminal window: {e}"


def run_micro_terminal_manager(visual_terminal_path, ai_model=None):
    """
    Interactive Micro Terminal Manager UI.  Runs its own input loop until the
    user types 'back' (return to main menu) or 'quit' (exit the application).

    Args:
        visual_terminal_path : Path to the visual terminal binary (e.g. xfce4-terminal).
        ai_model             : Optional AI model object (reserved for future AI-assisted
                               VM command suggestions).

    Returns:
        "back"  - caller should return to main mode selection.
        "quit"  - caller should exit the application.
    """
    print(f"\n{cyan}{'=' * 60}{reset}")
    print(f"{gold}        MICRO TERMINAL MANAGER{reset}")
    print(f"{cyan}{'=' * 60}{reset}")
    print(f"{blue}Deploy and manage lightweight terminal sessions for VMs.{reset}")
    print(f"{blue}Supports local shells, Docker containers, and SSH hosts.{reset}\n")

    while True:
        # Refresh and display the list of active micro terminals.
        active = list_micro_terminals()
        if active:
            print(f"\n{green}Active Micro Terminals ({len(active)}):{reset}")
            for i, term_name in enumerate(active, 1):
                print(f"  {gold}[{i}]{reset} {term_name}")
        else:
            print(f"\n{yellow}No active micro terminals.{reset}")

        print(f"\n{cyan}Commands:{reset}")
        print(f"  {gold}new <name>{reset}                    {blue}Create a local micro terminal{reset}")
        print(f"  {gold}new <name> docker <container>{reset}  {blue}Attach to a Docker container{reset}")
        print(f"  {gold}new <name> ssh <user@host>{reset}     {blue}Connect to a remote SSH host{reset}")
        print(f"  {gold}open <name>{reset}                   {blue}Open a micro terminal in a window{reset}")
        print(f"  {gold}send <name> <command>{reset}          {blue}Send a command to a micro terminal{reset}")
        print(f"  {gold}destroy <name>{reset}                {blue}Destroy a micro terminal session{reset}")
        print(f"  {gold}list{reset}                          {blue}Refresh the list{reset}")
        print(f"  {gold}back{reset}                          {blue}Return to main menu{reset}")
        print(f"  {gold}quit{reset}                          {blue}Exit Ai-Terminal-X{reset}")

        try:
            user_input = input(f"\n{green}Micro Terminal> {reset}").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return "quit"

        if not user_input:
            continue

        parts = user_input.split()
        cmd = parts[0].lower()

        if cmd in ("quit", "exit"):
            return "quit"

        elif cmd == "back":
            return "back"

        elif cmd == "list":
            continue  # The loop will redisplay the updated list.

        elif cmd == "new":
            if len(parts) < 2:
                print(f"{red}Usage: new <name> [docker <container> | ssh <user@host>]{reset}")
                continue
            term_name = parts[1]
            vm_type = "local"
            vm_target = None
            if len(parts) >= 4:
                vm_type = parts[2].lower()
                vm_target = parts[3]
            elif len(parts) == 3:
                print(f"{red}Usage: new <name> docker <container>  OR  new <name> ssh <user@host>{reset}")
                continue
            success, _session, msg = create_micro_terminal(term_name, vm_type, vm_target)
            if success:
                print(f"{green}✓ {msg}{reset}")
                try:
                    open_choice = input(
                        f"{cyan}Open '{term_name}' in a window now? (y/n): {reset}"
                    ).strip().lower()
                except (KeyboardInterrupt, EOFError):
                    print()
                    continue
                if open_choice in ("y", "yes"):
                    ok, open_msg = attach_micro_terminal(term_name, visual_terminal_path)
                    print(f"{green if ok else red}{'✓' if ok else '✗'} {open_msg}{reset}")
            else:
                print(f"{red}✗ {msg}{reset}")

        elif cmd == "open":
            if len(parts) < 2:
                print(f"{red}Usage: open <name>{reset}")
                continue
            ok, msg = attach_micro_terminal(parts[1], visual_terminal_path)
            print(f"{green if ok else red}{'✓' if ok else '✗'} {msg}{reset}")

        elif cmd == "send":
            if len(parts) < 3:
                print(f"{red}Usage: send <name> <command>{reset}")
                continue
            term_name = parts[1]
            command = " ".join(parts[2:])
            ok, msg = send_to_micro_terminal(term_name, command)
            print(f"{green if ok else red}{'✓' if ok else '✗'} {msg}{reset}")

        elif cmd == "destroy":
            if len(parts) < 2:
                print(f"{red}Usage: destroy <name>{reset}")
                continue
            term_name = parts[1]
            try:
                confirm = input(
                    f"{yellow}Destroy micro terminal '{term_name}'? (y/n): {reset}"
                ).strip().lower()
            except (KeyboardInterrupt, EOFError):
                print()
                continue
            if confirm in ("y", "yes"):
                ok, msg = destroy_micro_terminal(term_name)
                print(f"{green if ok else red}{'✓' if ok else '✗'} {msg}{reset}")
            else:
                print(f"{blue}Cancelled.{reset}")

        else:
            print(
                f"{yellow}Unknown command: '{cmd}'. "
                f"Type 'back' to return to the main menu.{reset}"
            )
