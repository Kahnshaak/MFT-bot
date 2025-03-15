# MFT-bot
## What is this bot even for??
With members of my friend group graduating college, moving away, having kids, and moving on with life in general, we wanted a way that we could keep in touch and still enjoy playing games together.
Eventually the concept of "Mandatory Fun Time" was born; a time that we would not make any plans, and just hang out doing whatever.
Often this included playing something like Among Us, or Jackbox, or maybe we would play Fortnite.

As our friend group grew, we invited more people to play, and the idea of what MFT was began evolving.
Different friends enjoyed different aspects of the game night and wanted something different.
In addition, schedules became more difficult to manage.

Regular Google Forms are much too cumbersome, and don't fit the need frankly.
Poll bots already in existance also don't meet the requirements.

## So like... what does it do?
I needed a bot that could:
 1. Assist in scheduling the game night
   - This included picking a date and time. We tried a standard meetup time, but that doesn't always work.
   - I needed the scheduling to be flexible enough that people can put in their availability, but also allow for making a firm decision on a start time
 2. Allow for polls on what activity we would do
   - This also needed some tuning, as the group decided that we wanted set times for different types of games (like a small-group game, and a large-group game)
 3. Separate from the game night, we need to be able to ping players for specific games
   - New games are always coming out, and sometimes those are contenders for game night. However, sometimes people want to play those outside the once-a-month occurance. This allows people to add themselves to a messaging queue so that if someone wants to play a game, they can just ping those interested without a million roles in the server, or an additional bot managing said million roles
 4. Also a bit of user management
   - Just to separate concerns, it can also allow a bit of user management for the bot's roles. Maybe you want everyone to be able to ping for games, but only like 3 people to ping for scheduling or something.

## Cool cool, tell me what we're using in this? Can I self-host?
### If you don't care about under-the-hood stuff, just skip this section.

This is written using Pycord, and utilizes MongoDB and Redis.
I am using KeyDB instead of Redis, cause I'm a FOSS bitch, but both are interchangeable in the commands.
Eventually I will get a Podman(Docker) container going so that it should be easy to deploy for your own server.
