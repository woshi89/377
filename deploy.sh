#!/bin/bash
# ============================================
# 骑行网站 - 阿里云服务器部署脚本
# 在阿里云网页终端中逐条执行以下命令
# ============================================

set -e

echo ">>> 1. 更新系统包"
sudo apt update && sudo apt upgrade -y

echo ">>> 2. 安装必要软件 (Python3, pip, git, nginx)"
sudo apt install -y python3 python3-pip python3-venv git nginx

echo ">>> 3. 克隆项目"
cd /home
sudo git clone https://github.com/woshi89/33.git /home/ride-site
sudo chown -R $USER:$USER /home/ride-site

echo ">>> 4. 创建虚拟环境并安装依赖"
cd /home/ride-site
python3 -m venv venv
source venv/bin/activate
pip install flask gunicorn
deactivate

echo ">>> 5. 配置 systemd 服务（开机自启）"
sudo tee /etc/systemd/system/ride-site.service > /dev/null << 'SERVICE'
[Unit]
Description=Ride Site Flask App
After=network.target

[Service]
User=$SUDO_USER
WorkingDirectory=/home/ride-site
ExecStart=/home/ride-site/venv/bin/gunicorn -w 4 -b 127.0.0.1:8000 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

# 替换 $SUDO_USER 为实际用户
sudo sed -i "s/User=\$SUDO_USER/User=$USER/" /etc/systemd/system/ride-site.service

sudo systemctl daemon-reload
sudo systemctl enable ride-site
sudo systemctl start ride-site

echo ">>> 6. 配置 Nginx 反向代理"
sudo tee /etc/nginx/sites-available/ride-site > /dev/null << 'NGINX'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
NGINX

sudo ln -sf /etc/nginx/sites-available/ride-site /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx

echo ">>> 7. 开放防火墙端口"
sudo ufw allow 80/tcp
sudo ufw allow 22/tcp
sudo ufw --force enable

echo ">>> 部署完成！在浏览器访问: http://你的服务器公网IP"
echo ">>> 检查服务状态: sudo systemctl status ride-site"
