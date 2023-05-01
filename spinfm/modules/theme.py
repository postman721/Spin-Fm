#Theme integrations

#Do not customize this part, unless adding themes
def theme_files(self):
    if theme == "dark":
        with open("/usr/share/sthemes/dark.css","r") as style:
            self.setStyleSheet(style.read())
    if theme == "blue":
        with open("/usr/share/sthemes/blue.css","r") as style:
            self.setStyleSheet(style.read())
    if theme == "green":
        with open("/usr/share/sthemes/green.css","r") as style:
            self.setStyleSheet(style.read())  
################################################


###########################
#This can be customized
###########################


#Set your theme here by changing the theme file between " "

#Supported values: 

		#	"dark"	  # Default theme with blue colors.
		# 	"blue"    # Blue theme.
		# 	"green"   # Green theme.		
		#   ""		  # Basic QT without CSS theming.



theme= "blue"
