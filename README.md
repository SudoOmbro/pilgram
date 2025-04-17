# Pilgram
a texting based idle MMO-RPG powered by AI.

<div>
  <img src="https://github.com/SudoOmbro/pilgram/blob/master/screenshots/img1.png" style=" width:200px ; height:200px" >
  <img src="https://github.com/SudoOmbro/pilgram/blob/master/screenshots/img2.png" style=" width:200px ; height:200px" >
  <img src="https://github.com/SudoOmbro/pilgram/blob/master/screenshots/img3.png" style=" width:200px ; height:200px" >
  <img src="https://github.com/SudoOmbro/pilgram/blob/master/screenshots/img4.png" style=" width:200px ; height:200px" >
  <img src="https://github.com/SudoOmbro/pilgram/blob/master/screenshots/img5.png" style=" width:200px ; height:200px" >
  <img src="https://github.com/SudoOmbro/pilgram/blob/master/screenshots/img6.png" style=" width:200px ; height:200px" >
  <img src="https://github.com/SudoOmbro/pilgram/blob/master/screenshots/img7.png" style=" width:200px ; height:200px" >
  <img src="https://github.com/SudoOmbro/pilgram/blob/master/screenshots/img8.png" style=" width:200px ; height:200px" >
</div>

Embark on quests, join guilds, play minigames, cast spells... All by texting!

The "main" version of pilgram is running on `@pilgram_bot` on Telegram if you want to try it out.

## Installation
**Note**: requires `Python >= 3.12.0`

1. Open a terminal
2. Move into a folder that doesn't have a folder named 'pilgram'
3. clone the repository with `git clone https://github.com/SudoOmbro/pilgram`
4. Move into the newly created pilgram folder with `cd pilgram`
5. Create a [Python virtual enviorment](https://docs.python.org/3/library/venv.html) with `python3.12 -m venv venv`
6. Activate the Python virtual enviorment with `source venv/bin/activate`
7. Install the requirements with `pip install -r requirements.txt`
8. Deactivate the Python virtual enviormante with `deactivate`
9. Configure (see next section)

## Configuration
Pilgram has 2 main config files: 
- `content_meta.json`: contains all the info about the world & the content in the game
- `settings.json`: contains general system settings like tokens & intervals

to Create `settings.json` simply rename `settings_template.json` or run `cp settings_template.json settings.json`, then proceed to change all XXX values to your own tokens.

## Deployment
Pilgram can be run simply by activating the Python virtual enviorment and then running the main file with `python main.py`. 
This is a simple but not ideal way of doing it, it does however give you easy access to the **Admin CLI**, which can be used to add content to the game and change some player values.

It is harder but preferable to deploy pilgram as a daemon on a linux server:

### systemd
here's how to deploy pilgram to a linux server:

Create a user and name it pilgram with `adduser pilgram`

Switch to the pilgram user with `su pilgram` and then move the the home directory with `cd`

Follow the same installation & configuration steps as described above, then run `sudo nano /etc/systemd/system/pilgram.service` and write the following:
```console
[Unit]
Description=pilgram service
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
Restart=always
RestartSec=1
User=pilgram
WorkingDirectory=/home/pilgram/pilgram
ExecStart=/home/pilgram/pilgram/venv/bin/python main.py
Sockets=pilgram.socket
StandardInput=socket
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```
Exit nano and save the buffer, then run `sudo nano /etc/systemd/system/pilgram.socket` and write the following:
```console
[Unit]
Description=pilgram socket
After=network.target
StartLimitIntervalSec=0

[Socket]
ListenFIFO=%t/pilgram.stdin
Service=pilgram.service
```
Again, exit nano and save.

Now that everything is set up, you can run `systemctl daemon-reload` to reaload all your daemons (and load the new ones you just added).
Now all that remains to do is starting your new daemons, so just run `systemctl start pilgram.socket` & `systemctl start pilgram.service` and everything should work fine.

You can check that everything is working by running `systemctl status pilgram.socket` & `systemctl status pilgram.service`.

This setup also lets you interact with the admin console by running `echo "command" > /run/pilgram.stdin`, which is very clunky to do honestly, which is why i suggest creating & using a bash function like this:
```console
wpc() {
  echo "$1" > /run/pilgram.stdin
  journalctl --unit=pilgram.service -n 1 --no-pager
}
```
by using this function the previous echo + piping thing just becomes `wpc "your command here"`, which is much more convenient.
