# Devmode Project --- Usage Guide

This README explains how to install, run, manage, update, and remove the
Devmode project.

The project supports multiple development modes and includes a project
manager tool to control everything from one place.

------------------------------------------------------------------------

# 1. First Installation

Download the project archive and extract it.

``` bash
tar -xzf devmode_project.tar.gz
cd devmode_project
```

Create your environment configuration file.

``` bash
cp .env.example .env
```

Edit the configuration.

``` bash
python3 project_manager.py edit-env
```

Bootstrap the project (creates virtual environment and installs
dependencies).

``` bash
python3 project_manager.py bootstrap --create-venv
```

Run setup.

``` bash
python3 project_manager.py setup
```

Start all enabled Devmodes.

``` bash
python3 project_manager.py start all
```

------------------------------------------------------------------------

# 2. Main Project Manager Commands

The main control script is:

    python3 project_manager.py

## Start Devmodes

Start all modes

``` bash
python3 project_manager.py start all
```

Start one mode

``` bash
python3 project_manager.py start Devmode1
```

## Stop Devmodes

Stop all modes

``` bash
python3 project_manager.py stop all
```

Stop a specific mode

``` bash
python3 project_manager.py stop Devmode2
```

## Restart Devmodes

``` bash
python3 project_manager.py restart Devmode4
```

------------------------------------------------------------------------


## Port allocation model

- Auth-enabled services (for example Devmode1/2) now run one listening port per user.
- Use `set-user-port` to pin a user to a fixed port or `random-user-port` to regenerate a random port.
- Non-auth services (for example Devmode3/4/5) support replicas using `DEVMODE*_REPLICAS` and the `set-replicas` command.
- Each replica can be pinned with `set-replica-port` or randomized with `random-replica-port`.

``` bash
python3 project_manager.py set-user-port Devmode1 alice 31001 --restart
python3 project_manager.py random-user-port Devmode1 alice --restart
python3 project_manager.py set-replicas Devmode3 3 --restart
python3 project_manager.py set-replica-port Devmode3 2 32002 --restart
python3 project_manager.py random-replica-port Devmode3 2 --restart
```

`status` now prints all active instances/ports for every mode.

------------------------------------------------------------------------

# 3. Status

Check status of all Devmodes.

``` bash
python3 project_manager.py status
```

------------------------------------------------------------------------

# 4. User Management

Add a user

``` bash
python3 project_manager.py add-user Devmode1 alice --password secret123
```

Remove a user

``` bash
python3 project_manager.py remove-user Devmode1 alice
```

List users

``` bash
python3 project_manager.py list-users all
```

Change user password

``` bash
python3 project_manager.py passwd Devmode1 alice --password newpass
```

------------------------------------------------------------------------

# 5. Environment Configuration

Edit the environment file.

``` bash
python3 project_manager.py edit-env
```

Reload environment variables.

``` bash
python3 project_manager.py load-env
```

------------------------------------------------------------------------

# 6. Update the Project

Pull updates from Git and restart services.

``` bash
python3 project_manager.py update --restart
```

------------------------------------------------------------------------

# 7. System Check

Check dependencies and configuration.

``` bash
python3 project_manager.py doctor
```

------------------------------------------------------------------------

# 8. Remove / Uninstall the Project

Remove runtime state.

``` bash
python3 project_manager.py remove --purge-state
```

Remove state and virtual environment.

``` bash
python3 project_manager.py remove --purge-state --remove-venv
```

------------------------------------------------------------------------

# 9. Install Global Command Launcher

This installs a command into `~/.local/bin`.

``` bash
python3 project_manager.py install-launcher
```

------------------------------------------------------------------------

# 10. Legacy Devmode Controller (Optional)

The repository still contains the old controller script.

Check status

``` bash
python3 devmodectl.py status
```

Start modes

``` bash
python3 devmodectl.py start
```

Stop modes

``` bash
python3 devmodectl.py stop
```

Restart modes

``` bash
python3 devmodectl.py restart
```

User management

``` bash
python3 devmodectl.py add-user --mode Devmode1 --username alice --password secret123
python3 devmodectl.py remove-user --mode Devmode1 --username alice
python3 devmodectl.py list-users --mode Devmode1
python3 devmodectl.py passwd --mode Devmode1 --username alice --password newpass
```

Environment management

``` bash
python3 devmodectl.py edit-env
python3 devmodectl.py load-env
```

------------------------------------------------------------------------

# 11. Git Repository Setup

Initialize repository.

``` bash
git init
git add .
git commit -m "Initial refactor for devmode project"
```

Connect to GitHub.

``` bash
git branch -M master
git remote add origin https://github.com/mahdidev3/devmode_project.git
git push -u origin master
```

------------------------------------------------------------------------

# 12. Using the Project on Another Machine

Clone the repository.

``` bash
git clone https://github.com/mahdidev3/devmode_project.git
cd devmode_project
```

Create environment file.

``` bash
cp .env.example .env
```

Edit `.env` and run setup.

``` bash
./setup_and_test.sh
```

Start Devmodes.

``` bash
python3 devmodectl.py start
```

------------------------------------------------------------------------

# Devmodes Included

The system supports the following Devmodes:

1.  Devmode1 --- HTTP + Authentication
2.  Devmode2 --- HTTPS + Authentication
3.  Devmode3 --- HTTP without Authentication
4.  Devmode4 --- HTTPS without Authentication
5.  Devmode5 --- Tunnel to another server

Each Devmode can be enabled or disabled in the `.env` file.

------------------------------------------------------------------------

# Adding New Devmodes

The project structure was designed to allow easy addition of new
Devmodes.\
Create a new module inside the Devmode directory and add configuration
entries in `.env`.

------------------------------------------------------------------------
