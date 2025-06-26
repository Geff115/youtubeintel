"""
Authentication routes for YouTubeIntel
Handles signup, signin, Google OAuth, password reset, email verification
"""

from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta
import uuid
import logging
from auth import auth_service, validate_input, token_required
from rate_limiter import rate_limit
from models import User, UserSession, db
from email_service import EmailService

logger = logging.getLogger(__name__)

# Create blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# Initialize email service
email_service = EmailService()

@auth_bp.route('/signup', methods=['POST'])
@rate_limit(credits_cost=0, limit_type='requests')
@validate_input(
    email={'required': True, 'type': str, 'validator': auth_service.validate_email, 'message': 'Invalid email format'},
    password={'required': True, 'type': str, 'min_length': 8, 'max_length': 128},
    first_name={'required': True, 'type': str, 'min_length': 2, 'max_length': 50, 'validator': auth_service.validate_name, 'message': 'Invalid first name'},
    last_name={'required': True, 'type': str, 'min_length': 2, 'max_length': 50, 'validator': auth_service.validate_name, 'message': 'Invalid last name'},
    age_confirmed={'required': True, 'type': bool},
    agreed_to_terms={'required': True, 'type': bool}
)
def traditional_signup():
    """Traditional email/password signup"""
    try:
        data = request.validated_data
        
        # Check if user already exists
        existing_user = User.query.filter_by(email=data['email'].lower()).first()
        if existing_user:
            return jsonify({'error': 'User already exists with this email'}), 409
        
        # Validate password strength
        password_validation = auth_service.validate_password(data['password'])
        if not password_validation['valid']:
            return jsonify({
                'error': 'Password does not meet requirements',
                'details': password_validation['errors']
            }), 400
        
        # Check terms and age confirmation
        if not data['age_confirmed']:
            return jsonify({'error': 'You must confirm that you are 18 years or older'}), 400
        
        if not data['agreed_to_terms']:
            return jsonify({'error': 'You must agree to the terms and conditions'}), 400
        
        # Create new user
        user = User(
            email=data['email'].lower(),
            first_name=data['first_name'].strip(),
            last_name=data['last_name'].strip(),
            auth_method='email',
            age_confirmed=True,
            agreed_to_terms=True,
            email_verified=False,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Set password
        user.set_password(data['password'])
        
        # Generate email verification token
        verification_token = user.generate_verification_token()
        
        # Save user
        db.session.add(user)
        db.session.commit()
        
        # Send verification email
        try:
            email_service.send_verification_email(
                user.email, 
                user.first_name, 
                verification_token
            )
            verification_sent = True
        except Exception as e:
            logger.error(f"Failed to send verification email: {str(e)}")
            verification_sent = False
        
        logger.info(f"New user registered: {user.email}")
        
        return jsonify({
            'success': True,
            'message': 'Account created successfully',
            'user': {
                'id': str(user.id),
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'email_verified': user.email_verified
            },
            'verification_email_sent': verification_sent,
            'next_step': 'Please check your email for verification link, then sign in'
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Signup failed: {str(e)}")
        return jsonify({'error': 'Account creation failed'}), 500

@auth_bp.route('/signup/google', methods=['POST'])
@rate_limit(credits_cost=0, limit_type='requests')
@validate_input(
    id_token={'required': True, 'type': str},
    age_confirmed={'required': True, 'type': bool},
    agreed_to_terms={'required': True, 'type': bool}
)
def google_signup():
    """Google OAuth signup"""
    try:
        data = request.validated_data
        
        # Verify Google token
        try:
            google_user = auth_service.verify_google_token(data['id_token'])
        except Exception as e:
            return jsonify({'error': 'Invalid Google token'}), 400
        
        # Check terms and age confirmation
        if not data['age_confirmed']:
            return jsonify({'error': 'You must confirm that you are 18 years or older'}), 400
        
        if not data['agreed_to_terms']:
            return jsonify({'error': 'You must agree to the terms and conditions'}), 400
        
        # Check if user already exists
        existing_user = User.query.filter_by(email=google_user['email'].lower()).first()
        if existing_user:
            if existing_user.auth_method == 'google':
                return jsonify({'error': 'Account already exists. Please sign in instead.'}), 409
            else:
                return jsonify({'error': 'An account with this email already exists with email/password authentication'}), 409
        
        # Create new user
        user = User(
            email=google_user['email'].lower(),
            first_name=google_user.get('first_name', ''),
            last_name=google_user.get('last_name', ''),
            display_name=google_user.get('name', ''),
            profile_picture=google_user.get('picture', ''),
            google_id=google_user['google_id'],
            auth_method='google',
            email_verified=google_user.get('email_verified', True),
            age_confirmed=True,
            agreed_to_terms=True,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Save user
        db.session.add(user)
        db.session.commit()
        
        logger.info(f"New Google user registered: {user.email}")
        
        return jsonify({
            'success': True,
            'message': 'Account created successfully with Google',
            'user': {
                'id': str(user.id),
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'display_name': user.display_name,
                'profile_picture': user.profile_picture,
                'email_verified': user.email_verified
            },
            'next_step': 'You can now sign in with Google'
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Google signup failed: {str(e)}")
        return jsonify({'error': 'Account creation failed'}), 500

@auth_bp.route('/signin', methods=['POST'])
@rate_limit(credits_cost=0, limit_type='requests')
@validate_input(
    email={'required': True, 'type': str, 'validator': auth_service.validate_email, 'message': 'Invalid email format'},
    password={'required': True, 'type': str}
)
def traditional_signin():
    """Traditional email/password signin"""
    try:
        data = request.validated_data
        
        # Find user
        user = User.query.filter_by(
            email=data['email'].lower(),
            auth_method='email'
        ).first()
        
        if not user or not user.verify_password(data['password']):
            return jsonify({'error': 'Invalid email or password'}), 401
        
        # Check if account is active
        if not user.is_active:
            return jsonify({'error': 'Account is deactivated. Please contact support.'}), 403
        
        # Generate tokens
        access_token = auth_service.generate_jwt_token(user.id, user.email, 'access')
        refresh_token = auth_service.generate_jwt_token(user.id, user.email, 'refresh')
        
        # Create session
        user.create_session(refresh_token)
        
        # Create session record
        session_record = UserSession(
            user_id=user.id,
            session_token=refresh_token,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', ''),
            device_info=_extract_device_info(request.headers.get('User-Agent', '')),
            expires_at=datetime.utcnow() + timedelta(days=30)
        )
        
        db.session.add(session_record)
        db.session.commit()
        
        logger.info(f"User signed in: {user.email}")
        
        return jsonify({
            'success': True,
            'message': 'Signed in successfully',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': user.to_dict(),
            'expires_in': 24 * 3600  # 24 hours
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Signin failed: {str(e)}")
        return jsonify({'error': 'Sign in failed'}), 500

@auth_bp.route('/signin/google', methods=['POST'])
@rate_limit(credits_cost=0, limit_type='requests')
@validate_input(
    id_token={'required': True, 'type': str}
)
def google_signin():
    """Google OAuth signin"""
    try:
        data = request.validated_data
        
        # Verify Google token
        try:
            google_user = auth_service.verify_google_token(data['id_token'])
        except Exception as e:
            return jsonify({'error': 'Invalid Google token'}), 400
        
        # Find user
        user = User.query.filter_by(
            email=google_user['email'].lower(),
            auth_method='google'
        ).first()
        
        if not user:
            return jsonify({
                'error': 'No account found with this Google account. Please sign up first.',
                'signup_required': True
            }), 404
        
        # Check if account is active
        if not user.is_active:
            return jsonify({'error': 'Account is deactivated. Please contact support.'}), 403
        
        # Update user info from Google ONLY if they don't have custom data
        # Don't overwrite display_name if user has set a custom one
        if not user.display_name or user.display_name == google_user.get('name', ''):
            user.display_name = google_user.get('name', user.display_name)
        
        # CRITICAL FIX: Only update profile picture from Google if:
        # 1. User doesn't have a profile picture, OR
        # 2. User's current profile picture is still a Google URL (not uploaded to Cloudinary)
        current_profile_picture = user.profile_picture
        google_profile_picture = google_user.get('picture', '')
        
        should_update_profile_picture = (
            not current_profile_picture or  # No profile picture
            (current_profile_picture and 'googleusercontent.com' in current_profile_picture)  # Still using Google picture
        )
        
        if should_update_profile_picture and google_profile_picture:
            user.profile_picture = google_profile_picture
            logger.info(f"Updated Google profile picture for {user.email}")
        else:
            logger.info(f"Preserved custom profile picture for {user.email}: {current_profile_picture}")
        
        # Always update email verification status from Google
        user.email_verified = google_user.get('email_verified', user.email_verified)
        
        # Generate tokens
        access_token = auth_service.generate_jwt_token(user.id, user.email, 'access')
        refresh_token = auth_service.generate_jwt_token(user.id, user.email, 'refresh')
        
        # Create session
        user.create_session(refresh_token)
        
        # Create session record
        session_record = UserSession(
            user_id=user.id,
            session_token=refresh_token,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', ''),
            device_info=_extract_device_info(request.headers.get('User-Agent', '')),
            expires_at=datetime.utcnow() + timedelta(days=30)
        )
        
        db.session.add(session_record)
        db.session.commit()
        
        logger.info(f"Google user signed in: {user.email}")
        
        return jsonify({
            'success': True,
            'message': 'Signed in successfully with Google',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': user.to_dict(),
            'expires_in': 24 * 3600  # 24 hours
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Google signin failed: {str(e)}")
        return jsonify({'error': 'Sign in failed'}), 500

@auth_bp.route('/google/callback', methods=['POST'])
@rate_limit(credits_cost=0, limit_type='requests')
@validate_input(
    code={'required': True, 'type': str}
)
def google_oauth_callback():
    """Exchange Google authorization code for tokens"""
    try:
        data = request.validated_data
        code = data['code']

        # Exchange authorization code for tokens
        client_id = os.getenv('GOOGLE_CLIENT_ID')
        client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
        redirect_uri = os.getenv('GOOGLE_REDIRECT_URI', 'postmessage')  # 'postmessage' is for client-side flows

        # Make request to Google token endpoint
        token_url = 'https://oauth2.googleapis.com/token'
        token_data = {
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code'
        }

        token_response = requests.post(token_url, data=token_data)
        if not token_response.ok:
            logger.error(f"Google token exchange failed: {token_response.text}")
            return jsonify({'error': 'Failed to exchange authorization code for tokens'}), 400
        
        token_info = token_response.json()
        id_token = token_info.get('id_token')

        if not id_token:
            return jsonify({'error': 'No ID token received from Google'}), 400
        
        # Verify the ID token
        google_user = auth_service.verify_google_token(id_token)

        # Return the ID token to the client
        return jsonify({
            'success': True,
            'message': 'Google OAuth successful',
            'id_token': id_token,
            'user_info': google_user
        }), 200
    
    except Exception as e:
        logger.error(f"Google OAuth callback failed: {str(e)}")
        return jsonify({'error': 'Failed to process Google authentication'}), 500

@auth_bp.route('/refresh', methods=['POST'])
@validate_input(
    refresh_token={'required': True, 'type': str}
)
def refresh_token():
    """Refresh access token using refresh token"""
    try:
        data = request.validated_data
        
        # Verify refresh token
        try:
            payload = auth_service.verify_jwt_token(data['refresh_token'])
            
            if payload['token_type'] != 'refresh':
                raise Exception("Invalid token type")
                
        except Exception as e:
            return jsonify({'error': 'Invalid refresh token'}), 401
        
        # Find user and verify session
        user = User.query.get(payload['user_id'])
        if not user or not user.is_active:
            return jsonify({'error': 'User not found or inactive'}), 404
        
        # Check if session is still valid
        if not user.is_session_valid() or user.refresh_token != data['refresh_token']:
            return jsonify({'error': 'Session expired. Please sign in again.'}), 401
        
        # Generate new access token
        new_access_token = auth_service.generate_jwt_token(user.id, user.email, 'access')
        
        # Update activity
        user.update_activity()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'access_token': new_access_token,
            'expires_in': 24 * 3600  # 24 hours
        }), 200
        
    except Exception as e:
        logger.error(f"Token refresh failed: {str(e)}")
        return jsonify({'error': 'Token refresh failed'}), 500

@auth_bp.route('/forgot-password', methods=['POST'])
@rate_limit(credits_cost=0, limit_type='requests')
@validate_input(
    email={'required': True, 'type': str, 'validator': auth_service.validate_email, 'message': 'Invalid email format'}
)
def forgot_password():
    """Request password reset"""
    try:
        data = request.validated_data
        
        # Find user
        user = User.query.filter_by(
            email=data['email'].lower(),
            auth_method='email'
        ).first()
        
        # Always return success to prevent email enumeration
        response_message = "If an account with this email exists, you will receive password reset instructions."
        
        if user and user.is_active:
            # Generate reset token
            reset_token = user.generate_reset_token()
            db.session.commit()
            
            # Send reset email
            try:
                email_service.send_password_reset_email(
                    user.email,
                    user.first_name,
                    reset_token
                )
                logger.info(f"Password reset email sent to: {user.email}")
            except Exception as e:
                logger.error(f"Failed to send reset email: {str(e)}")
        
        return jsonify({
            'success': True,
            'message': response_message
        }), 200
        
    except Exception as e:
        logger.error(f"Forgot password failed: {str(e)}")
        return jsonify({'error': 'Request failed. Please try again.'}), 500

@auth_bp.route('/reset-password', methods=['POST'])
@rate_limit(credits_cost=0, limit_type='requests')
@validate_input(
    token={'required': True, 'type': str},
    new_password={'required': True, 'type': str, 'min_length': 8, 'max_length': 128}
)
def reset_password():
    """Reset password with token"""
    try:
        data = request.validated_data
        
        # Find user with reset token
        user = User.query.filter_by(reset_token=data['token']).first()
        
        if not user or not user.reset_token_expires or datetime.utcnow() > user.reset_token_expires:
            return jsonify({'error': 'Invalid or expired reset token'}), 400
        
        # Validate new password
        password_validation = auth_service.validate_password(data['new_password'])
        if not password_validation['valid']:
            return jsonify({
                'error': 'Password does not meet requirements',
                'details': password_validation['errors']
            }), 400
        
        # Update password
        user.set_password(data['new_password'])
        user.reset_token = None
        user.reset_token_expires = None
        
        # Clear all sessions for security
        user.clear_session()
        UserSession.query.filter_by(user_id=user.id).update({'is_active': False})
        
        db.session.commit()
        
        logger.info(f"Password reset for user: {user.email}")
        
        return jsonify({
            'success': True,
            'message': 'Password reset successfully. Please sign in with your new password.'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Password reset failed: {str(e)}")
        return jsonify({'error': 'Password reset failed'}), 500

@auth_bp.route('/verify-email', methods=['POST'])
@validate_input(
    token={'required': True, 'type': str}
)
def verify_email():
    """Verify email address with token"""
    try:
        data = request.validated_data
        
        # Find user with verification token
        user = User.query.filter_by(verification_token=data['token']).first()
        
        if not user or not user.verification_token_expires or datetime.utcnow() > user.verification_token_expires:
            return jsonify({'error': 'Invalid or expired verification token'}), 400
        
        # Verify email
        user.verify_email()
        db.session.commit()
        
        logger.info(f"Email verified for user: {user.email}")
        
        return jsonify({
            'success': True,
            'message': 'Email verified successfully!'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Email verification failed: {str(e)}")
        return jsonify({'error': 'Email verification failed'}), 500

@auth_bp.route('/resend-verification', methods=['POST'])
@rate_limit(credits_cost=0, limit_type='requests')
@validate_input(
    email={'required': True, 'type': str, 'validator': auth_service.validate_email, 'message': 'Invalid email format'}
)
def resend_verification():
    """Resend email verification"""
    try:
        data = request.validated_data
        
        user = User.query.filter_by(email=data['email'].lower()).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if user.email_verified:
            return jsonify({'error': 'Email is already verified'}), 400
        
        # Generate new verification token
        verification_token = user.generate_verification_token()
        db.session.commit()
        
        # Send verification email
        try:
            email_service.send_verification_email(
                user.email,
                user.first_name,
                verification_token
            )
        except Exception as e:
            logger.error(f"Failed to send verification email: {str(e)}")
            return jsonify({'error': 'Failed to send verification email'}), 500
        
        return jsonify({
            'success': True,
            'message': 'Verification email sent successfully'
        }), 200
        
    except Exception as e:
        logger.error(f"Resend verification failed: {str(e)}")
        return jsonify({'error': 'Failed to resend verification'}), 500

@auth_bp.route('/signout', methods=['POST'])
@validate_input(
    refresh_token={'required': False, 'type': str}
)
def signout():
    """Sign out user and invalidate session"""
    try:
        data = request.validated_data
        refresh_token = data.get('refresh_token')
        
        if refresh_token:
            try:
                payload = auth_service.verify_jwt_token(refresh_token)
                user = User.query.get(payload['user_id'])
                
                if user:
                    # Clear user session
                    user.clear_session()
                    
                    # Deactivate session records
                    UserSession.query.filter_by(
                        user_id=user.id, 
                        session_token=refresh_token
                    ).update({'is_active': False})
                    
                    db.session.commit()
                    logger.info(f"User signed out: {user.email}")
                    
            except Exception as e:
                logger.error(f"Session cleanup failed during signout: {str(e)}")
        
        return jsonify({
            'success': True,
            'message': 'Signed out successfully'
        }), 200
        
    except Exception as e:
        logger.error(f"Signout failed: {str(e)}")
        return jsonify({'error': 'Signout failed'}), 500

@auth_bp.route('/me', methods=['GET'])
@token_required
def get_current_user():
    """Get current user information"""
    try:
        # Now request.current_user will be properly set by the decorator
        user = User.query.get(request.current_user['id'])
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Update activity
        user.update_activity()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        logger.error(f"Get current user failed: {str(e)}")
        return jsonify({'error': 'Failed to get user information'}), 500

@auth_bp.route('/sessions', methods=['GET'])
def get_user_sessions():
    """Get user's active sessions"""
    from auth import token_required
    
    @token_required
    def _get_sessions():
        try:
            user_id = request.current_user['id']
            
            sessions = UserSession.query.filter_by(
                user_id=user_id,
                is_active=True
            ).order_by(UserSession.last_activity.desc()).all()
            
            return jsonify({
                'success': True,
                'sessions': [session.to_dict() for session in sessions]
            }), 200
            
        except Exception as e:
            logger.error(f"Get sessions failed: {str(e)}")
            return jsonify({'error': 'Failed to get sessions'}), 500
    
    return _get_sessions()

@auth_bp.route('/sessions/<session_id>', methods=['DELETE'])
def revoke_session(session_id):
    """Revoke a specific session"""
    from auth import token_required
    
    @token_required
    def _revoke_session():
        try:
            user_id = request.current_user['id']
            
            session = UserSession.query.filter_by(
                id=session_id,
                user_id=user_id,
                is_active=True
            ).first()
            
            if not session:
                return jsonify({'error': 'Session not found'}), 404
            
            session.deactivate()
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Session revoked successfully'
            }), 200
            
        except Exception as e:
            logger.error(f"Session revocation failed: {str(e)}")
            return jsonify({'error': 'Failed to revoke session'}), 500
    
    return _revoke_session()

@auth_bp.route('/change-password', methods=['POST'])
@validate_input(
    current_password={'required': True, 'type': str},
    new_password={'required': True, 'type': str, 'min_length': 8, 'max_length': 128}
)
def change_password():
    """Change user password"""
    from auth import token_required
    
    @token_required
    def _change_password():
        try:
            data = request.validated_data
            user = User.query.get(request.current_user['id'])
            
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            if user.auth_method != 'email':
                return jsonify({'error': 'Password change not available for Google accounts'}), 400
            
            # Verify current password
            if not user.verify_password(data['current_password']):
                return jsonify({'error': 'Current password is incorrect'}), 400
            
            # Validate new password
            password_validation = auth_service.validate_password(data['new_password'])
            if not password_validation['valid']:
                return jsonify({
                    'error': 'New password does not meet requirements',
                    'details': password_validation['errors']
                }), 400
            
            # Update password
            user.set_password(data['new_password'])
            
            # Clear all other sessions for security
            UserSession.query.filter(
                UserSession.user_id == user.id,
                UserSession.session_token != user.refresh_token
            ).update({'is_active': False})
            
            db.session.commit()
            
            logger.info(f"Password changed for user: {user.email}")
            
            return jsonify({
                'success': True,
                'message': 'Password changed successfully'
            }), 200
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Password change failed: {str(e)}")
            return jsonify({'error': 'Password change failed'}), 500
    
    return _change_password()

# Helper functions
def _extract_device_info(user_agent: str) -> str:
    """Extract device information from user agent"""
    user_agent = user_agent.lower()
    
    if 'mobile' in user_agent or 'android' in user_agent:
        if 'android' in user_agent:
            return 'Android Mobile'
        elif 'iphone' in user_agent:
            return 'iPhone'
        else:
            return 'Mobile Device'
    elif 'tablet' in user_agent or 'ipad' in user_agent:
        return 'Tablet'
    elif 'windows' in user_agent:
        return 'Windows PC'
    elif 'mac' in user_agent:
        return 'Mac'
    elif 'linux' in user_agent:
        return 'Linux'
    else:
        return 'Unknown Device'