"""
Email service for YouTubeIntel authentication
Handles verification emails, password reset, and other notifications
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import logging
from typing import Optional
import requests
import json

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        # Email configuration
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_username = os.getenv('SMTP_USERNAME')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.from_email = os.getenv('FROM_EMAIL', self.smtp_username)
        self.from_name = os.getenv('FROM_NAME', 'YouTubeIntel')
        
        # App configuration
        self.app_url = os.getenv('APP_URL', 'https://youtubeintel-backend.onrender.com')
        self.frontend_url = os.getenv('FRONTEND_URL', 'http://youtubeintel.vercel.app')
        
        # Resend (recommended for production)
        self.resend_api_key = os.getenv('RESEND_API_KEY')
        
        # Alternative: Mailgun (if configured)
        self.mailgun_api_key = os.getenv('MAILGUN_API_KEY')
        self.mailgun_domain = os.getenv('MAILGUN_DOMAIN')
        
        # Alternative: SendGrid (if configured)
        self.sendgrid_api_key = os.getenv('SENDGRID_API_KEY')
        
        # Check if email is configured
        self.is_configured = bool(
            self.resend_api_key or
            (self.smtp_username and self.smtp_password) or 
            (self.mailgun_api_key and self.mailgun_domain) or 
            self.sendgrid_api_key
        )
        
        if not self.is_configured:
            logger.warning("Email service not configured - email features will be disabled")
    
    def send_email(self, to_email: str, subject: str, html_content: str, 
                   text_content: Optional[str] = None) -> bool:
        """Send email using configured service"""
        if not self.is_configured:
            logger.warning(f"Email not configured - would send: {subject} to {to_email}")
            return False
        
        try:
            # Try Resend first (most reliable and modern)
            if self.resend_api_key:
                return self._send_resend(to_email, subject, html_content, text_content)
            
            # Try Mailgun
            elif self.mailgun_api_key and self.mailgun_domain:
                return self._send_mailgun(to_email, subject, html_content, text_content)
            
            # Try SendGrid
            elif self.sendgrid_api_key:
                return self._send_sendgrid(to_email, subject, html_content, text_content)
            
            # Fall back to SMTP
            elif self.smtp_username and self.smtp_password:
                return self._send_smtp(to_email, subject, html_content, text_content)
            
            else:
                logger.error("No email service configured")
                return False
                
        except Exception as e:
            logger.error(f"Email sending failed: {str(e)}")
            return False
    
    def _send_resend(self, to_email: str, subject: str, html_content: str, 
                     text_content: Optional[str] = None) -> bool:
        """Send email via Resend (recommended)"""
        try:
            url = "https://api.resend.com/emails"
            
            # Prepare email data
            email_data = {
                "from": f"{self.from_name} <notifications@youtubeintel.com>",  # Use your verified domain
                "to": [to_email],
                "subject": subject,
                "html": html_content
            }
            
            # Add text content if provided
            if text_content:
                email_data["text"] = text_content
            
            # Set headers
            headers = {
                "Authorization": f"Bearer {self.resend_api_key}",
                "Content-Type": "application/json"
            }
            
            # Send request
            response = requests.post(url, headers=headers, json=email_data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                email_id = result.get('id', 'unknown')
                logger.info(f"Email sent successfully via Resend to: {to_email} (ID: {email_id})")
                return True
            else:
                error_data = response.json() if response.headers.get('content-type') == 'application/json' else {}
                error_message = error_data.get('message', response.text)
                logger.error(f"Resend email failed: {response.status_code} - {error_message}")
                return False
                
        except Exception as e:
            logger.error(f"Resend email failed: {str(e)}")
            return False
    
    def _send_smtp(self, to_email: str, subject: str, html_content: str, 
                   text_content: Optional[str] = None) -> bool:
        """Send email via SMTP"""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email
            
            # Add text part
            if text_content:
                text_part = MIMEText(text_content, 'plain')
                msg.attach(text_part)
            
            # Add HTML part
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Send email
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            
            text = msg.as_string()
            server.sendmail(self.from_email, to_email, text)
            server.quit()
            
            logger.info(f"Email sent successfully via SMTP to: {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"SMTP email failed: {str(e)}")
            return False
    
    def _send_mailgun(self, to_email: str, subject: str, html_content: str, 
                      text_content: Optional[str] = None) -> bool:
        """Send email via Mailgun"""
        try:
            url = f"https://api.mailgun.net/v3/{self.mailgun_domain}/messages"
            
            data = {
                'from': f"{self.from_name} <noreply@{self.mailgun_domain}>",
                'to': to_email,
                'subject': subject,
                'html': html_content
            }
            
            if text_content:
                data['text'] = text_content
            
            response = requests.post(
                url,
                auth=('api', self.mailgun_api_key),
                data=data,
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"Email sent successfully via Mailgun to: {to_email}")
                return True
            else:
                logger.error(f"Mailgun email failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Mailgun email failed: {str(e)}")
            return False
    
    def _send_sendgrid(self, to_email: str, subject: str, html_content: str, 
                       text_content: Optional[str] = None) -> bool:
        """Send email via SendGrid"""
        try:
            url = "https://api.sendgrid.com/v3/mail/send"
            
            data = {
                "personalizations": [{
                    "to": [{"email": to_email}]
                }],
                "from": {
                    "email": self.from_email,
                    "name": self.from_name
                },
                "subject": subject,
                "content": [
                    {
                        "type": "text/html",
                        "value": html_content
                    }
                ]
            }
            
            if text_content:
                data["content"].append({
                    "type": "text/plain",
                    "value": text_content
                })
            
            headers = {
                'Authorization': f'Bearer {self.sendgrid_api_key}',
                'Content-Type': 'application/json'
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 202:
                logger.info(f"Email sent successfully via SendGrid to: {to_email}")
                return True
            else:
                logger.error(f"SendGrid email failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"SendGrid email failed: {str(e)}")
            return False
    
    def send_verification_email(self, email: str, first_name: str, verification_token: str) -> bool:
        """Send email verification email"""
        verification_url = f"{self.frontend_url}/auth/verify-email?token={verification_token}"
        
        subject = "Verify your YouTubeIntel account"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Verify Your Email</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 20px; text-align: center; }}
                .logo {{ color: #ffffff; font-size: 28px; font-weight: bold; margin: 0; }}
                .content {{ padding: 40px 30px; }}
                .title {{ color: #333333; font-size: 24px; margin-bottom: 20px; }}
                .text {{ color: #555555; font-size: 16px; line-height: 1.6; margin-bottom: 30px; }}
                .button {{ display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #ffffff; text-decoration: none; padding: 15px 30px; border-radius: 8px; font-weight: bold; font-size: 16px; }}
                .button:hover {{ opacity: 0.9; }}
                .footer {{ background-color: #f8f9fa; padding: 20px; text-align: center; color: #888888; font-size: 14px; }}
                .link {{ color: #667eea; word-break: break-all; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 class="logo">YouTubeIntel</h1>
                </div>
                <div class="content">
                    <h2 class="title">Welcome to YouTubeIntel, {first_name}! 🎉</h2>
                    <p class="text">
                        Thank you for signing up! To get started with discovering YouTube channels and growing your audience, 
                        please verify your email address by clicking the button below.
                    </p>
                    <p class="text">
                        <a href="{verification_url}" class="button">Verify Email Address</a>
                    </p>
                    <p class="text">
                        If the button doesn't work, you can copy and paste this link into your browser:
                        <br><a href="{verification_url}" class="link">{verification_url}</a>
                    </p>
                    <p class="text">
                        Once verified, you'll get <strong>25 free credits</strong> to start exploring our channel discovery features!
                    </p>
                </div>
                <div class="footer">
                    <p>This verification link will expire in 24 hours.</p>
                    <p>If you didn't create an account with YouTubeIntel, you can safely ignore this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
        Welcome to YouTubeIntel, {first_name}!
        
        Thank you for signing up! To get started, please verify your email address by visiting:
        {verification_url}
        
        Once verified, you'll get 25 free credits to start exploring our channel discovery features!
        
        This verification link will expire in 24 hours.
        If you didn't create an account with YouTubeIntel, you can safely ignore this email.
        """
        
        return self.send_email(email, subject, html_content, text_content)
    
    def send_password_reset_email(self, email: str, first_name: str, reset_token: str) -> bool:
        """Send password reset email"""
        reset_url = f"{self.frontend_url}/auth/reset-password?token={reset_token}"
        
        subject = "Reset your YouTubeIntel password"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Reset Your Password</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 20px; text-align: center; }}
                .logo {{ color: #ffffff; font-size: 28px; font-weight: bold; margin: 0; }}
                .content {{ padding: 40px 30px; }}
                .title {{ color: #333333; font-size: 24px; margin-bottom: 20px; }}
                .text {{ color: #555555; font-size: 16px; line-height: 1.6; margin-bottom: 30px; }}
                .button {{ display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #ffffff; text-decoration: none; padding: 15px 30px; border-radius: 8px; font-weight: bold; font-size: 16px; }}
                .button:hover {{ opacity: 0.9; }}
                .footer {{ background-color: #f8f9fa; padding: 20px; text-align: center; color: #888888; font-size: 14px; }}
                .link {{ color: #667eea; word-break: break-all; }}
                .warning {{ background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin-bottom: 20px; color: #856404; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 class="logo">YouTubeIntel</h1>
                </div>
                <div class="content">
                    <h2 class="title">Password Reset Request</h2>
                    <p class="text">Hi {first_name},</p>
                    <p class="text">
                        We received a request to reset your password for your YouTubeIntel account. 
                        Click the button below to create a new password:
                    </p>
                    <p class="text">
                        <a href="{reset_url}" class="button">Reset Password</a>
                    </p>
                    <p class="text">
                        If the button doesn't work, you can copy and paste this link into your browser:
                        <br><a href="{reset_url}" class="link">{reset_url}</a>
                    </p>
                    <div class="warning">
                        <strong>Security Notice:</strong> This link will expire in 1 hour for your security. 
                        If you didn't request this password reset, please ignore this email.
                    </div>
                </div>
                <div class="footer">
                    <p>This password reset link will expire in 1 hour.</p>
                    <p>For security, all your active sessions will be logged out when you reset your password.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
        Password Reset Request
        
        Hi {first_name},
        
        We received a request to reset your password for your YouTubeIntel account.
        Visit this link to create a new password:
        {reset_url}
        
        This link will expire in 1 hour for your security.
        If you didn't request this password reset, please ignore this email.
        
        For security, all your active sessions will be logged out when you reset your password.
        """
        
        return self.send_email(email, subject, html_content, text_content)
    
    def send_welcome_email(self, email: str, first_name: str) -> bool:
        """Send welcome email after email verification"""
        subject = "Welcome to YouTubeIntel! 🚀"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Welcome to YouTubeIntel</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 20px; text-align: center; }}
                .logo {{ color: #ffffff; font-size: 28px; font-weight: bold; margin: 0; }}
                .content {{ padding: 40px 30px; }}
                .title {{ color: #333333; font-size: 24px; margin-bottom: 20px; }}
                .text {{ color: #555555; font-size: 16px; line-height: 1.6; margin-bottom: 20px; }}
                .feature {{ background-color: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
                .feature h3 {{ color: #333333; margin-top: 0; }}
                .button {{ display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #ffffff; text-decoration: none; padding: 15px 30px; border-radius: 8px; font-weight: bold; font-size: 16px; margin: 10px 5px; }}
                .credits {{ background: linear-gradient(135deg, #00b894 0%, #00cec9 100%); color: white; padding: 20px; border-radius: 8px; text-align: center; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 class="logo">YouTubeIntel</h1>
                </div>
                <div class="content">
                    <h2 class="title">Welcome aboard, {first_name}! 🎉</h2>
                    
                    <div class="credits">
                        <h3 style="margin-top: 0;">🎁 You've got 25 FREE credits!</h3>
                        <p style="margin-bottom: 0;">Start discovering amazing YouTube channels right away!</p>
                    </div>
                    
                    <p class="text">
                        You're now part of the YouTubeIntel community! Here's what you can do with your platform:
                    </p>
                    
                    <div class="feature">
                        <h3>🔍 Discover Related Channels</h3>
                        <p>Find channels similar to yours or your competitors using 6 different discovery methods.</p>
                    </div>
                    
                    <div class="feature">
                        <h3>📊 Deep Analytics</h3>
                        <p>Get comprehensive channel metadata, subscriber counts, video analytics, and growth insights.</p>
                    </div>
                    
                    <div class="feature">
                        <h3>⚡ Batch Processing</h3>
                        <p>Process thousands of channels at once with our powerful batch processing tools.</p>
                    </div>
                    
                    <div class="feature">
                        <h3>📈 Export Data</h3>
                        <p>Export your findings to CSV, JSON, or integrate with your existing tools.</p>
                    </div>
                    
                    <p class="text">Ready to start exploring? Click below to access your dashboard:</p>
                    
                    <p style="text-align: center;">
                        <a href="{self.frontend_url}/dashboard" class="button">Go to Dashboard</a>
                        <a href="{self.frontend_url}/discover" class="button">Start Discovering</a>
                    </p>
                    
                    <p class="text">
                        Need help? Check out our <a href="{self.frontend_url}/docs">documentation</a> or 
                        <a href="mailto:support@youtubeintel.com">contact our support team</a>.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
        Welcome aboard, {first_name}!
        
        🎁 You've got 25 FREE credits to start discovering amazing YouTube channels!
        
        Here's what you can do with YouTubeIntel:
        
        🔍 Discover Related Channels
        Find channels similar to yours or your competitors using 6 different discovery methods.
        
        📊 Deep Analytics
        Get comprehensive channel metadata, subscriber counts, video analytics, and growth insights.
        
        ⚡ Batch Processing
        Process thousands of channels at once with our powerful batch processing tools.
        
        📈 Export Data
        Export your findings to CSV, JSON, or integrate with your existing tools.
        
        Ready to start? Visit your dashboard: {self.frontend_url}/dashboard
        
        Need help? Contact us at support@youtubeintel.com
        """
        
        return self.send_email(email, subject, html_content, text_content)