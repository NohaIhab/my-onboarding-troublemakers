This is a bundle containing two related charms.
The bundle however has been hastily written and is plagued by some nasty bugs.
Your task is to fix the bundle. 

Luckily someone thought about test-driven development.

Have fun!

# Instructions for use
Use this repository **as template** (don't fork it!) 
![image](https://user-images.githubusercontent.com/6230162/192721247-d8a58106-9b15-4211-8dc4-89be1311ab40.png)

to create a **private** repo in your own name (not Canonical).
![image](https://user-images.githubusercontent.com/6230162/192721996-241a5246-094c-422c-bf99-812682eb865b.png)

# Success conditions
Consider your task done when:

 - `tox` succeeds locally
 - your branch passes the CI on GH.

## Tips and Tricks

### Keep tox-managed model
To instruct the testing env to deploy the charms to a model called 'task' 
and not destroy it after the tests are done, run:

`tox --model task --keep-models`

This can be useful for debugging once a specific test fails.

### Look into `juju debug-code` and `juju debug-hooks`

Just do that.

### Live-testing the webapp-db integration
At some point `juju status` should show (IPs might differ):

```text
Unit          Workload  Agent  Address       Ports  Message
database/0*   active    idle   10.1.232.190
webserver/0   active    idle   10.1.232.166
webserver/1*  active    idle   10.1.232.167
webserver/2   active    idle   10.1.232.156
```

Open in a browser:
`10.1.232.166:8000` and it should show 'ready' if everything is OK.

`10.1.232.166:8000/docs` to see the FastAPI swagger UI.
Via the ui, you should be able to store and retrieve key/value pairs from the database.
