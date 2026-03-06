#!/bin/bash

sudo apt-get install -y socat

sudo bash -c "cat > /etc/systemd/system/proxypi.service" << EOF
[Unit]
Description=Proxypi Access Unix socket server
After=network.target

[Service]
Environment=TERM=xterm-256color
WorkingDirectory=/home/admin
ExecStartPre=rm -f /tmp/proxypi.sock
ExecStart=socat UNIX-LISTEN:/tmp/proxypi.sock,fork,mode=777 EXEC:/home/admin/proxypi_socket.sh
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable proxypi
sudo systemctl restart proxypi
sudo systemctl status proxypi
