# Hermes API 2.0 Interface

### Install

1) create python 3.9 virtual environment by using pyenv or your favourite method
2) pipenv install --dev  


#### Single project version with messaging

1) Ensure Postgres and Rabbit MQ services are running on local machines.

2) For full development system run:
    API, Dispatch, Correct number of Consumers, Updater Services by running the
    appropriate commands in separate terminal windows.
    
3) Hermes must be running or linked to.


To see current list of commands:

```shell
    pipenv run python commands.py --help 
```
to see current list of commands

For example runs the development werkzeug server:

```shell
    pipenv run python commands.py run-api-server
```

To run up Hermes API messaging using command line requires a .env to be added to the project directory
and will be read when using pipenv run. To build an excample .env run

```shell
    pipenv run python commands.py write-example-env
```
Remember to edit the .env for your test environment and do not commit.

#### PyCharm Running and Debugging

Typically PyCharm expects to run and debug using configurations. This requires more work to
set up but is easier for frequently users and for debugging via an IDE. You will need a configuration for each service
eg API, Dispatch, Consumers, Retry and Updater
Set up pycharm by creating configurations with: 

    script = "/PycharmProjects/hermes_api/commands.py"
    parameter = the command eg "run-api-server".

Also the same environment variables must be set in each configuration.  This can be done in a terminal 
by running ```manage write-example-env``` to create an .env file.  After editing, select all lines and 
copy the selection then paste into the configuration form's environmental variables.
If one service is correct it can be duplicated and only needs the name and command
parameter amended.



## Commands:
* `pipenv run python commands.py write-example-env`  
  Run the above command in the project directory to create an example .env file
  
* `pipenv run python commands.py run-api-server`  
  Runs a development/debug server 
  
### Run as production server with Gunicorn:

from top project  directory:
pipenv run gunicorn -b 0.0.0.0:5000 main:app
     

 ## Environment Variables
 #### Common env variables:
- `LOG_LEVEL`
  - Log messages with this level or above. e.g. "DEBUG"
- `JWT_SECRET`
  - Signing secret for JWT authentication
- `DATABASE_USER`
  - Username to use for auth with Postgres
- `DATABASE_PASSWORD`
  - Password to use for auth with Postgres
- `DATABASE_HOST`
  - Host for Postgres, e.g. "http://127.0.0.1". Needs protocol at start
- `DATABASE_PORT`
  - Port for Postgres, e.g. "8529"
- `RABBIT_USER`
  - Username to use for auth with RabbitMQ
- `RABBIT_PASSWORD`
  - Password to use for auth with RabbitMQ
- `RABBIT_HOST`
  - IP address for RabbitMQ, e.g. "127.0.0.1"
- `RABBIT_PORT`
  - Port for RabbitMQ, e.g. "5672"


#### API env variables:
- `URL_PREFIX`
  - Sets prefix for url path. Defaults to "api2" so a request to
    membership plan would go to "/api2/membership_plan"

#### Retry env variables:
- `RETRY_TIME`
  - Only retry messages older than x seconds (max. retry period is 1200s or 20 mins)
- `RETRY_INCREASE`
  - Increase retry time by x seconds each failed retry (max. retry period is 1200s or 20 mins)
- `MESSAGE_LOG_TIME_LIMIT`
  - Deletes message logs which are older than x hours

    
#### Required Services For a Functional Hermes:
1)  Api server use manage run-api-server - multiple instances typically required

Note:  Hermes must be running with messaging enabled in environment variables.

