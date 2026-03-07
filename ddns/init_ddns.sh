#!/bin/bash

# Script to add DDNS cron job if it doesn't already exist
# Execute from /home/admin

CRON_LINE="*/5 * * * * /home/admin/ddns/ovh_ddns.sh"
CRON_COMMENT="# OVH DDNS Update"

echo "Checking if DDNS cron job exists..."

# Check if the cron job already exists
if crontab -l 2>/dev/null | grep -qF "/home/admin/ddns/ovh_ddns.sh"; then
    echo -e "✓ DDNS cron job already exists. No changes needed.\n"
else
    echo "Adding DDNS cron job to crontab..."

    # Add the cron job (preserve existing crontab)
    (crontab -l 2>/dev/null; echo ""; echo "$CRON_COMMENT"; echo "$CRON_LINE") | crontab -

    if [ $? -eq 0 ]; then
        echo "✓ Successfully added DDNS cron job!\n"
        echo "Added line:"
        echo "  $CRON_LINE\n"
        echo "This will run the DDNS update script every 5 minutes."
    else
        echo "✗ Failed to add cron job. Please check permissions."
        exit 1
    fi
fi
