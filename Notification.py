from smsmobileapi import SMSSender

sms = SMSSender(api_key='2d40b5fcbd8ad8ec1bfddd64eefab95df70cdb8d10baed3a')
response = sms.send_message(to='+79663711888', message='Привет от Python!')
print(response)
