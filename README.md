# onion_farmer
Need to add some more Sec Onion automation in your life? Look no further! Given a 2.3.30 ISO, and a proper YAML based config file you too can have your very own customized installer.

![Boot screen](../assets/screenshot.png?raw=true)

What this will do is render out some automation templates, which have been slighty modifed from what [Security Onion Solutions](https://securityonionsolutions.com/) already provides. Take those templates and re-master an ISO with them added as boot options.

Once you boot into the selected option, a simple one-line command (```auto_setup```) is all that is needed to start the automated install process!

```./farmer.py -i < UNC path to 2.3.30 ISO > -c < config file > -d < destination for built iso >```



$sudo ./farmer.py -i ${PWD}/securityonion-2.3.30.iso -c config.yml -d /tmp/auto_seconion.iso
