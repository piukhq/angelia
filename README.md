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

## Monitoring

On localhost you can define in .env (see commands)
    
    PERFORMANCE_METRICS=1

Run the following command to view messages:

    while true;do;nc localhost  -l 4000;echo "\n";done
    
    
## URLS and Resources and Models
### URLS
see in resources file urls.py which contains a def associating and end point url (hint) to a resource class
Resources can use the endpoint url in different ways but non standard use merits a comment

### Resources
each resource class handles one url endpoint and associated methods.
  
They are identical Falcon resources except we use a base class to make it easier to handle dynamic sessions and to set
 up the url endpoint.  This allows resources to overide or not extend from Base class inorder to set up a different url
 ignoring or using in a different way the url defined in urls.py 

### Models
The models are maintained in Hermes using Django.
Sqlalchamy has matching classes for each table which are defined using reflection. This means only the
relationships need to be defined which cannot be abstracted from Postgres.  However, autocomplete with respect
to table contents will not work in the IDE but can be referenced in classes 

Example query in a resource end point method where user and user detail are one to one:

    # Reflect each database table we need to use, using metadata
    class User(Base):
        __table__ = Table('user', metadata, autoload=True)
        profile = relationship("UserDetail", backref="user", uselist=False)   # uselist = False sets one to one relation


    class UserDetail(Base):
        __table__ = Table('user_userdetail', metadata, autoload=True)
 
 
Note use of self.session in resource class which is read only for gets and write for other methods

       for user in self.session.query(User).filter(User.email.like('%bink%')).order_by(User.id):
            if user.profile.first_name:
                print(user.id, user.email, user.external_id, user.profile.first_name)



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
- `POSTGRES_READ_DSN`
   - Read Postgres DSN e.g. postgresql://user:pass@host:port/databasename
- `POSTGRES_WRITE_DSN` 
   - Write Postgres DSN e.g. postgresql://user:pass@host:port/databasename
- `RABBIT_USER`
  - Username to use for auth with RabbitMQ
- `RABBIT_PASSWORD`
  - Password to use for auth with RabbitMQ
- `RABBIT_HOST`
  - IP address for RabbitMQ, e.g. "127.0.0.1"
- `RABBIT_PORT`
  - Port for RabbitMQ, e.g. "5672"
- `HERMES_URL`
  - Hermes API address
- `METRICS_SIDECAR_DOMAIN`
    - Metrics domain set to =localhost
- `METRICS_PORT`
    - Metrics port set to =4000
- `PERFORMANCE_METRICS`
    - Metrics performance set to send ie =1


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

