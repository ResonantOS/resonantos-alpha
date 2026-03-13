# Notification Rules
# ResonantOS Logician

ntf_cron_category(/fix, /routine).
ntf_cron_category(/backup, /routine).
ntf_cron_category(/cleanup, /routine).
ntf_cron_category(/maintenance, /routine).
ntf_cron_category(/monitor, /actionable).
ntf_cron_category(/security, /critical).
ntf_cron_category(/alert, /critical).
ntf_cron_category(/research, /routine).

ntf_cron_delivery(/routine, /success, /silent).
ntf_cron_delivery(/routine, /failure, /notify).
ntf_cron_delivery(/actionable, /success, /notify).
ntf_cron_delivery(/actionable, /failure, /notify).
ntf_cron_delivery(/critical, /success, /notify).
ntf_cron_delivery(/critical, /failure, /notify).

ntf_quiet_hour_delivery(/critical, /notify).
ntf_quiet_hour_delivery(/actionable, /defer).
ntf_quiet_hour_delivery(/routine, /silent).

ntf_notification_priority(/critical, /immediate).
ntf_notification_priority(/actionable, /respect_quiet).
ntf_notification_priority(/routine, /silent).
