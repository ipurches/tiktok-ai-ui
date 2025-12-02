import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import logging
import hashlib

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="TikTok Marketing Automation",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #FF0050;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        margin: 0;
    }
    .metric-label {
        font-size: 0.9rem;
        opacity: 0.9;
        margin: 0;
    }
    .status-badge {
        padding: 0.25rem 0.75rem;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .status-pending {
        background-color: #FFA500;
        color: white;
    }
    .status-published {
        background-color: #28a745;
        color: white;
    }
    .status-rejected {
        background-color: #dc3545;
        color: white;
    }
    .login-container {
        max-width: 400px;
        margin: 100px auto;
        padding: 2rem;
        background: white;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'username' not in st.session_state:
    st.session_state.username = None
if 'db_connection' not in st.session_state:
    st.session_state.db_connection = None

def get_db_connection():
    """Create database connection (only once after login)"""
    if st.session_state.db_connection and not st.session_state.db_connection.closed:
        return st.session_state.db_connection
    
    try:
        host = os.getenv('DB_HOST')
        port = os.getenv('DB_PORT', '5432')
        database = os.getenv('DB_NAME', 'postgres')
        user = os.getenv('DB_USER')
        password = os.getenv('DB_PASSWORD')
        
        logger.info(f"Connecting to database")
        
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            cursor_factory=RealDictCursor,
            connect_timeout=10,
            sslmode='require'
        )
        
        st.session_state.db_connection = conn
        logger.info("Database connection established successfully")
        return conn
        
    except Exception as e:
        logger.error(f"Connection failed: {str(e)}")
        st.error(f"Database connection failed: {str(e)}")
        return None

def verify_login(username, password):
    """Verify login credentials against database"""
    try:
        conn = get_db_connection()
        if not conn:
            return False
        
        with conn.cursor() as cur:
            cur.execute(
                "SELECT verify_dashboard_password(%s, %s) as is_valid",
                (username, password)
            )
            result = cur.fetchone()
            
            if result and result['is_valid']:
                # Update last login
                cur.execute(
                    "UPDATE dashboard_users SET last_login = NOW() WHERE username = %s",
                    (username,)
                )
                conn.commit()
                logger.info(f"User {username} logged in successfully")
                return True
            else:
                logger.warning(f"Failed login attempt for user: {username}")
                return False
                
    except Exception as e:
        logger.error(f"Login verification failed: {str(e)}")
        return False

def login_page():
    """Display login page"""
    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    
    st.markdown('<h1 style="text-align: center; color: #FF0050;">🔐 Login</h1>', unsafe_allow_html=True)
    st.markdown('<p style="text-align: center; color: #666;">TikTok Marketing Automation Dashboard</p>', unsafe_allow_html=True)
    
    with st.form("login_form"):
        username = st.text_input("Username", placeholder="Enter username")
        password = st.text_input("Password", type="password", placeholder="Enter password")
        submit = st.form_submit_button("Login", use_container_width=True)
        
        if submit:
            if verify_login(username, password):
                st.session_state.authenticated = True
                st.session_state.username = username
                st.success("Login successful!")
                st.rerun()
            else:
                st.error("Invalid username or password")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    st.caption("Contact administrator for login credentials")

def logout():
    """Logout and close database connection"""
    if st.session_state.db_connection and not st.session_state.db_connection.closed:
        st.session_state.db_connection.close()
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.db_connection = None
    st.rerun()

def execute_query(query, params=None, fetch=True):
    """Execute database query with error handling"""
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return None
        
        with conn.cursor() as cur:
            cur.execute(query, params)
            if fetch:
                result = cur.fetchall()
                logger.info(f"Query executed successfully, returned {len(result)} rows")
                return result
            else:
                conn.commit()
                logger.info("Query executed successfully, changes committed")
                return True
                
    except Exception as e:
        logger.error(f"Query execution failed: {str(e)}")
        if conn and not conn.closed:
            try:
                conn.rollback()
            except:
                pass
        st.error(f"Query execution failed: {str(e)}")
        return None

def send_approval_webhook(content_id, action, reason=None):
    """Send approval/rejection to n8n webhook"""
    webhook_url = os.getenv('N8N_WEBHOOK_URL')
    
    if not webhook_url:
        logger.error("N8N_WEBHOOK_URL not configured")
        st.error("Webhook URL not configured")
        return False
    
    payload = {
        "content_id": content_id,
        "action": action
    }
    
    if reason:
        payload["reason"] = reason
    
    try:
        logger.info(f"Sending {action} request for content_id: {content_id}")
        response = requests.post(webhook_url, json=payload, timeout=30)
        response.raise_for_status()
        logger.info(f"Webhook request successful: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"Webhook request failed: {str(e)}")
        st.error(f"Failed to send approval: {str(e)}")
        return False

def get_upload_post_analytics():
    """Get analytics from Upload-Post API"""
    api_key = os.getenv('UPLOAD_POST_API_KEY')
    profile = os.getenv('UPLOAD_POST_PROFILE', 'ipurchase')
    
    if not api_key:
        logger.warning("Upload-Post API key not configured")
        return None
    
    try:
        url = f"https://api.upload-post.com/api/analytics/{profile}"
        headers = {"Authorization": f"Apikey {api_key}"}
        params = {"platforms": "tiktok,facebook,youtube"}
        
        logger.info(f"Fetching analytics for profile: {profile}")
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        logger.info("Analytics fetched successfully")
        return response.json()
    except Exception as e:
        logger.error(f"Failed to fetch analytics: {str(e)}")
        return None

# Check authentication
if not st.session_state.authenticated:
    login_page()
    st.stop()

# Sidebar navigation (after login)
st.sidebar.title(f"Welcome, {st.session_state.username}!")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    ["Dashboard Overview", "Product Management", "Content Review", 
     "Content Calendar", "Analytics Dashboard", "Settings"]
)

# Logout button
if st.sidebar.button("🚪 Logout", use_container_width=True):
    logout()

# Quick stats in sidebar
st.sidebar.markdown("---")
st.sidebar.subheader("Quick Stats")

# Get Upload-Post analytics for sidebar
analytics_data = get_upload_post_analytics()

if analytics_data:
    tiktok_data = analytics_data.get('tiktok', {})
    facebook_data = analytics_data.get('facebook', {})
    youtube_data = analytics_data.get('youtube', {})
    
    total_followers = (
        tiktok_data.get('followers', 0) + 
        facebook_data.get('followers', 0) + 
        youtube_data.get('subscribers', 0)
    )
    
    total_views = (
        tiktok_data.get('videoViews', 0) + 
        facebook_data.get('videoViews', 0) + 
        youtube_data.get('views', 0)
    )
    
    st.sidebar.metric("Total Followers", f"{total_followers:,}")
    st.sidebar.metric("Total Views", f"{total_views:,}")

stats_query = """
SELECT 
    (SELECT COUNT(*) FROM products) as total_products,
    (SELECT COUNT(*) FROM content WHERE status = 'pending_review') as pending_review,
    (SELECT COUNT(*) FROM posts WHERE status = 'published') as published_posts
"""
stats = execute_query(stats_query)

if stats:
    st.sidebar.metric("Total Products", stats[0]['total_products'])
    st.sidebar.metric("Pending Review", stats[0]['pending_review'])
    st.sidebar.metric("Published Posts", stats[0]['published_posts'])

st.sidebar.markdown("---")
st.sidebar.caption("TikTok Marketing Automation v1.0")

# PAGE 1: DASHBOARD OVERVIEW
if page == "Dashboard Overview":
    st.markdown('<h1 class="main-header">📊 Dashboard Overview</h1>', unsafe_allow_html=True)
    
    # Get real-time analytics from Upload-Post API
    api_key = os.getenv('UPLOAD_POST_API_KEY')
    profile = os.getenv('UPLOAD_POST_PROFILE', 'ipurchase')
    
    if api_key:
        try:
            # Fetch analytics
            url = f"https://api.upload-post.com/api/analytics/{profile}"
            headers = {"Authorization": f"Apikey {api_key}"}
            params = {"platforms": "instagram,tiktok,youtube,facebook,linkedin,x,threads,pinterest,reddit,bluesky"}
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            analytics = response.json()
            
            # Fetch upload history to count videos per platform
            history_url = "https://api.upload-post.com/api/uploadposts/history"
            history_response = requests.get(
                history_url, 
                headers=headers, 
                params={"page": 1, "limit": 100}, 
                timeout=30
            )
            history_response.raise_for_status()
            history_data = history_response.json()
            
            # Count videos per platform
            video_counts = {}
            for item in history_data.get('history', []):
                platform = item.get('platform')
                if platform:
                    video_counts[platform] = video_counts.get(platform, 0) + 1
            
            # Display platform-specific metrics
            st.subheader("📱 Platform Analytics")
            
            # TikTok
            tiktok = analytics.get('tiktok', {})
            if tiktok and not tiktok.get('success') == False:
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.markdown(f"""
                    <div class="metric-card">
                        <p class="metric-label">TikTok Followers</p>
                        <p class="metric-value">{tiktok.get('followers', 0):,}</p>
                    </div>
                    """, unsafe_allow_html=True)
                with col2:
                    st.markdown(f"""
                    <div class="metric-card">
                        <p class="metric-label">TikTok Views</p>
                        <p class="metric-value">{tiktok.get('reach', 0):,}</p>
                    </div>
                    """, unsafe_allow_html=True)
                with col3:
                    st.markdown(f"""
                    <div class="metric-card">
                        <p class="metric-label">TikTok Impressions</p>
                        <p class="metric-value">{tiktok.get('impressions', 0):,}</p>
                    </div>
                    """, unsafe_allow_html=True)
                with col4:
                    st.markdown(f"""
                    <div class="metric-card">
                        <p class="metric-label">TikTok Videos</p>
                        <p class="metric-value">{video_counts.get('tiktok', 0):,}</p>
                    </div>
                    """, unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # YouTube
            youtube = analytics.get('youtube', {})
            if youtube and not youtube.get('success') == False:
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.markdown(f"""
                    <div class="metric-card">
                        <p class="metric-label">YouTube Followers</p>
                        <p class="metric-value">{youtube.get('followers', 0):,}</p>
                    </div>
                    """, unsafe_allow_html=True)
                with col2:
                    st.markdown(f"""
                    <div class="metric-card">
                        <p class="metric-label">YouTube Views</p>
                        <p class="metric-value">{youtube.get('reach', 0):,}</p>
                    </div>
                    """, unsafe_allow_html=True)
                with col3:
                    st.markdown(f"""
                    <div class="metric-card">
                        <p class="metric-label">YouTube Impressions</p>
                        <p class="metric-value">{youtube.get('impressions', 0):,}</p>
                    </div>
                    """, unsafe_allow_html=True)
                with col4:
                    st.markdown(f"""
                    <div class="metric-card">
                        <p class="metric-label">YouTube Videos</p>
                        <p class="metric-value">{video_counts.get('youtube', 0):,}</p>
                    </div>
                    """, unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Instagram
            instagram = analytics.get('instagram', {})
            if instagram and not instagram.get('success') == False:
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.markdown(f"""
                    <div class="metric-card">
                        <p class="metric-label">Instagram Followers</p>
                        <p class="metric-value">{instagram.get('followers', 0):,}</p>
                    </div>
                    """, unsafe_allow_html=True)
                with col2:
                    st.markdown(f"""
                    <div class="metric-card">
                        <p class="metric-label">Instagram Views</p>
                        <p class="metric-value">{instagram.get('reach', 0):,}</p>
                    </div>
                    """, unsafe_allow_html=True)
                with col3:
                    st.markdown(f"""
                    <div class="metric-card">
                        <p class="metric-label">Instagram Impressions</p>
                        <p class="metric-value">{instagram.get('impressions', 0):,}</p>
                    </div>
                    """, unsafe_allow_html=True)
                with col4:
                    st.markdown(f"""
                    <div class="metric-card">
                        <p class="metric-label">Instagram Videos</p>
                        <p class="metric-value">{video_counts.get('instagram', 0):,}</p>
                    </div>
                    """, unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Facebook
            facebook = analytics.get('facebook', {})
            if facebook and not facebook.get('success') == False:
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.markdown(f"""
                    <div class="metric-card">
                        <p class="metric-label">Facebook Followers</p>
                        <p class="metric-value">{facebook.get('followers', 0):,}</p>
                    </div>
                    """, unsafe_allow_html=True)
                with col2:
                    st.markdown(f"""
                    <div class="metric-card">
                        <p class="metric-label">Facebook Views</p>
                        <p class="metric-value">{facebook.get('reach', 0):,}</p>
                    </div>
                    """, unsafe_allow_html=True)
                with col3:
                    st.markdown(f"""
                    <div class="metric-card">
                        <p class="metric-label">Facebook Impressions</p>
                        <p class="metric-value">{facebook.get('impressions', 0):,}</p>
                    </div>
                    """, unsafe_allow_html=True)
                with col4:
                    st.markdown(f"""
                    <div class="metric-card">
                        <p class="metric-label">Facebook Videos</p>
                        <p class="metric-value">{video_counts.get('facebook', 0):,}</p>
                    </div>
                    """, unsafe_allow_html=True)
            
            # Total summary
            st.markdown("---")
            total_followers = (
                tiktok.get('followers', 0) + 
                youtube.get('followers', 0) + 
                instagram.get('followers', 0) + 
                facebook.get('followers', 0)
            )
            total_views = (
                tiktok.get('reach', 0) + 
                youtube.get('reach', 0) + 
                instagram.get('reach', 0) + 
                facebook.get('reach', 0)
            )
            total_impressions = (
                tiktok.get('impressions', 0) + 
                youtube.get('impressions', 0) + 
                instagram.get('impressions', 0) + 
                facebook.get('impressions', 0)
            )
            total_videos = sum(video_counts.values())
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.markdown(f"""
                <div style="text-align: center; padding: 1rem;">
                    <h3 style="color: #667eea;">Total Followers</h3>
                    <h1 style="color: #FF0050; font-size: 2.5rem;">{total_followers:,}</h1>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                st.markdown(f"""
                <div style="text-align: center; padding: 1rem;">
                    <h3 style="color: #667eea;">Total Views</h3>
                    <h1 style="color: #FF0050; font-size: 2.5rem;">{total_views:,}</h1>
                </div>
                """, unsafe_allow_html=True)
            with col3:
                st.markdown(f"""
                <div style="text-align: center; padding: 1rem;">
                    <h3 style="color: #667eea;">Total Impressions</h3>
                    <h1 style="color: #FF0050; font-size: 2.5rem;">{total_impressions:,}</h1>
                </div>
                """, unsafe_allow_html=True)
            with col4:
                st.markdown(f"""
                <div style="text-align: center; padding: 1rem;">
                    <h3 style="color: #667eea;">Total Videos</h3>
                    <h1 style="color: #FF0050; font-size: 2.5rem;">{total_videos:,}</h1>
                </div>
                """, unsafe_allow_html=True)
            
        except Exception as e:
            logger.error(f"Failed to fetch analytics: {str(e)}")
            st.error(f"Unable to fetch analytics data: {str(e)}")
    else:
        st.warning("Upload-Post API key not configured")
    
    st.markdown("---")
    
    # Database metrics
    metrics_query = """
    SELECT 
        (SELECT COUNT(*) FROM products) as total_products,
        (SELECT COUNT(*) FROM content WHERE status = 'pending_review') as pending_review,
        (SELECT COUNT(*) FROM posts WHERE status = 'published') as published_posts
    """
    
    metrics = execute_query(metrics_query)
    
    if metrics:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Products", metrics[0]['total_products'])
        with col2:
            st.metric("Pending Review", metrics[0]['pending_review'])
        with col3:
            st.metric("Published Posts", metrics[0]['published_posts'])
    
    st.markdown("---")
    
    # Recent published posts
    st.subheader("Recent Published Posts")
    
    recent_posts_query = """
    SELECT 
        p.post_url,
        p.platform,
        p.published_at,
        c.caption,
        pr.title as product_title
    FROM posts p
    JOIN content c ON p.content_id = c.id
    JOIN products pr ON c.product_id = pr.id
    WHERE p.status = 'published'
    ORDER BY p.published_at DESC
    LIMIT 5
    """
    
    recent_posts = execute_query(recent_posts_query)
    
    if recent_posts and len(recent_posts) > 0:
        for post in recent_posts:
            with st.container():
                col1, col2, col3 = st.columns([2, 3, 2])
                with col1:
                    st.write(f"**{post['product_title']}**")
                with col2:
                    st.write(post['caption'][:100] + "..." if len(post['caption']) > 100 else post['caption'])
                with col3:
                    st.write(f"**{post['platform']}** | {post['published_at'].strftime('%Y-%m-%d %H:%M')}")
                    if post['post_url']:
                        st.link_button("View Post", post['post_url'], use_container_width=True)
                st.markdown("---")
    else:
        st.info("No published posts yet. Start by approving content!")

# PAGE 2: PRODUCT MANAGEMENT
elif page == "Product Management":
    st.markdown('<h1 class="main-header">🛍️ Product Management</h1>', unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["📤 Upload Product", "📋 View Products"])
    
    # TAB 1: UPLOAD PRODUCT
    with tab1:
        st.info("ℹ️ **Note:** Products uploaded here will be added to the database for content generation. This does not add them to your official TikTok Shop or Shopify store.")
        
        st.subheader("Add New Product")
        
        with st.form("product_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                product_id = st.text_input(
                    "Product ID *", 
                    placeholder="e.g., PROD-12345",
                    help="Unique identifier for this product"
                )
                
                title = st.text_input(
                    "Product Title *", 
                    placeholder="e.g., Premium Leather Wallet - Handcrafted Italian Design",
                    help="Descriptive title (60+ characters recommended for SEO)"
                )
                
                price = st.number_input(
                    "Price (€) *", 
                    min_value=0.0, 
                    step=0.01, 
                    format="%.2f",
                    help="Product price in Euros"
                )
                
                category = st.selectbox(
                    "Category *", 
                    ["Accessories", "Electronics", "Clothing", "Home & Living", "Beauty & Health", "Sports & Outdoors", "Toys & Games", "Food & Beverages", "Books & Media", "Other"],
                    help="Product category"
                )
            
            with col2:
                source = st.selectbox(
                    "Source *", 
                    ["manual", "shopify", "tiktok_shop"],
                    help="Where this product comes from"
                )
                
                shopify_url = st.text_input(
                    "Shopify URL (Optional)", 
                    placeholder="https://ipurches.myshopify.com/products/...",
                    help="Link to Shopify product page"
                )
                
                tiktok_shop_url = st.text_input(
                    "TikTok Shop URL (Optional)", 
                    placeholder="https://www.tiktok.com/@ipurches/product/...",
                    help="Link to TikTok Shop product"
                )
                
                image_urls = st.text_area(
                    "Image URLs (Optional)",
                    placeholder="https://example.com/image1.jpg\nhttps://example.com/image2.jpg\nhttps://example.com/image3.jpg",
                    help="One URL per line. Add up to 5 product images.",
                    height=100
                )
            
            description = st.text_area(
                "Description *", 
                placeholder="Detailed product description highlighting key features, benefits, and specifications...",
                help="Detailed product description for content generation",
                height=150
            )
            
            st.markdown("---")
            
            col1, col2, col3 = st.columns([1, 1, 2])
            
            with col1:
                submitted = st.form_submit_button("✅ Add Product", use_container_width=True, type="primary")
            
            with col2:
                if st.form_submit_button("🔄 Clear Form", use_container_width=True):
                    st.rerun()
            
            if submitted:
                # Validation
                if not product_id or not title or not description:
                    st.error("❌ Product ID, Title, and Description are required fields")
                elif price <= 0:
                    st.error("❌ Price must be greater than 0")
                else:
                    try:
                        # Process image URLs
                        images_list = []
                        if image_urls:
                            images_list = [url.strip() for url in image_urls.split('\n') if url.strip()]
                            # Limit to 5 images
                            images_list = images_list[:5]
                        
                        # Convert to PostgreSQL array format
                        if images_list:
                            images_array = "{" + ",".join([f'"{url}"' for url in images_list]) + "}"
                        else:
                            images_array = "{}"
                        
                        # Insert query
                        insert_query = """
                        INSERT INTO products (
                            source, 
                            product_id, 
                            title, 
                            description, 
                            price, 
                            category, 
                            images, 
                            shopify_url, 
                            tiktok_shop_url, 
                            status,
                            created_at,
                            updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending_content_generation', NOW(), NOW())
                        """
                        
                        result = execute_query(
                            insert_query,
                            (source, product_id, title, description, price, category, images_array, shopify_url or None, tiktok_shop_url or None),
                            fetch=False
                        )
                        
                        if result:
                            logger.info(f"Product added successfully: {product_id}")
                            st.success(f"✅ Product '{title}' added successfully!")
                            st.balloons()
                            st.info("💡 The content generation workflow will automatically create video content for this product within the next hour.")
                        else:
                            st.error("❌ Failed to add product. Please check if Product ID already exists.")
                    
                    except Exception as e:
                        logger.error(f"Error adding product: {str(e)}")
                        st.error(f"❌ Error: {str(e)}")
    
    # TAB 2: VIEW PRODUCTS
    with tab2:
        st.subheader("Product Catalog")
        
        # Filters
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            filter_source = st.selectbox(
                "Source", 
                ["All", "manual", "shopify", "tiktok_shop"]
            )
        
        with col2:
            filter_status = st.selectbox(
                "Status", 
                ["All", "pending_content_generation", "content_generated", "published"]
            )
        
        with col3:
            filter_category = st.selectbox(
                "Category",
                ["All", "Accessories", "Electronics", "Clothing", "Home & Living", "Beauty & Health", "Sports & Outdoors", "Toys & Games", "Food & Beverages", "Books & Media", "Other"]
            )
        
        with col4:
            search_term = st.text_input("🔍 Search", placeholder="Search by title...")
        
        # Build query
        query = """
        SELECT 
            id,
            product_id,
            title,
            description,
            price,
            category,
            source,
            status,
            images,
            shopify_url,
            tiktok_shop_url,
            created_at,
            updated_at
        FROM products 
        WHERE 1=1
        """
        params = []
        
        if filter_source != "All":
            query += " AND source = %s"
            params.append(filter_source)
        
        if filter_status != "All":
            query += " AND status = %s"
            params.append(filter_status)
        
        if filter_category != "All":
            query += " AND category = %s"
            params.append(filter_category)
        
        if search_term:
            query += " AND title ILIKE %s"
            params.append(f"%{search_term}%")
        
        query += " ORDER BY created_at DESC LIMIT 50"
        
        products = execute_query(query, params if params else None)
        
        if products and len(products) > 0:
            st.write(f"**Found {len(products)} product(s)**")
            st.markdown("---")
            
            # Display products as cards with images
            for product in products:
                with st.expander(f"**{product['title']}** - €{float(product['price']):.2f}", expanded=False):
                    col1, col2 = st.columns([1, 2])
                    
                    with col1:
                        # Display product image
                        if product['images'] and len(product['images']) > 0:
                            try:
                                # Get first image
                                first_image = product['images'][0]
                                st.image(first_image, use_container_width=True, caption="Product Image")
                                
                                # Show additional images if available
                                if len(product['images']) > 1:
                                    with st.popover("📷 View All Images"):
                                        for i, img_url in enumerate(product['images'], 1):
                                            st.image(img_url, caption=f"Image {i}", use_container_width=True)
                                            st.markdown("---")
                            except Exception as e:
                                st.image("https://via.placeholder.com/400x400.png?text=No+Image", use_container_width=True)
                                st.caption("⚠️ Image unavailable")
                        else:
                            st.image("https://via.placeholder.com/400x400.png?text=No+Image", use_container_width=True)
                            st.caption("No images available")
                    
                    with col2:
                        # Product details
                        st.write(f"**Product ID:** `{product['product_id']}`")
                        st.write(f"**Category:** {product['category']}")
                        st.write(f"**Source:** {product['source']}")
                        
                        # Status badge
                        status_color = {
                            'pending_content_generation': 'orange',
                            'content_generated': 'blue',
                            'published': 'green'
                        }
                        st.markdown(f"**Status:** :{status_color.get(product['status'], 'gray')}[{product['status']}]")
                        
                        st.write(f"**Created:** {product['created_at'].strftime('%Y-%m-%d %H:%M')}")
                        
                        # Description
                        st.markdown("**Description:**")
                        description_preview = product['description'][:200] + "..." if len(product['description']) > 200 else product['description']
                        st.write(description_preview)
                        
                        if len(product['description']) > 200:
                            with st.popover("📄 Read Full Description"):
                                st.write(product['description'])
                        
                        # Links
                        link_col1, link_col2 = st.columns(2)
                        
                        with link_col1:
                            if product['shopify_url']:
                                st.link_button("🛒 View on Shopify", product['shopify_url'], use_container_width=True)
                        
                        with link_col2:
                            if product['tiktok_shop_url']:
                                st.link_button("🎵 View on TikTok", product['tiktok_shop_url'], use_container_width=True)
                        
                        # Actions
                        st.markdown("---")
                        action_col1, action_col2 = st.columns(2)
                        
                        with action_col1:
                            if st.button("🔄 Regenerate Content", key=f"regen_{product['id']}", use_container_width=True):
                                # Update status to trigger content generation
                                update_query = """
                                UPDATE products 
                                SET status = 'pending_content_generation', updated_at = NOW()
                                WHERE id = %s
                                """
                                if execute_query(update_query, (product['id'],), fetch=False):
                                    st.success("✅ Product queued for content regeneration!")
                                    st.rerun()
                        
                        with action_col2:
                            if st.button("🗑️ Delete Product", key=f"delete_{product['id']}", use_container_width=True, type="secondary"):
                                st.session_state[f"confirm_delete_{product['id']}"] = True
                        
                        # Delete confirmation
                        if st.session_state.get(f"confirm_delete_{product['id']}", False):
                            st.warning("⚠️ Are you sure? This will also delete all related content and posts.")
                            conf_col1, conf_col2 = st.columns(2)
                            
                            with conf_col1:
                                if st.button("✅ Yes, Delete", key=f"confirm_yes_{product['id']}", type="primary"):
                                    delete_query = "DELETE FROM products WHERE id = %s"
                                    if execute_query(delete_query, (product['id'],), fetch=False):
                                        st.success("Product deleted successfully!")
                                        logger.info(f"Product deleted: {product['id']}")
                                        del st.session_state[f"confirm_delete_{product['id']}"]
                                        st.rerun()
                            
                            with conf_col2:
                                if st.button("❌ Cancel", key=f"confirm_no_{product['id']}"):
                                    del st.session_state[f"confirm_delete_{product['id']}"]
                                    st.rerun()
                    
                    st.markdown("---")
        
        else:
            st.info("📭 No products found. Add your first product using the 'Upload Product' tab!")
            
            # Quick stats
            stats_query = """
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'pending_content_generation') as pending,
                COUNT(*) FILTER (WHERE status = 'content_generated') as generated,
                COUNT(*) FILTER (WHERE status = 'published') as published
            FROM products
            """
            
            stats = execute_query(stats_query)
            
            if stats:
                st.markdown("---")
                st.subheader("Product Statistics")
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Total Products", stats[0]['total'])
                col2.metric("Pending Content", stats[0]['pending'])
                col3.metric("Content Generated", stats[0]['generated'])
                col4.metric("Published", stats[0]['published'])


# PAGE 3: CONTENT REVIEW (with video preview fix)
# PAGE 3: CONTENT REVIEW (with improved video preview)
elif page == "Content Review":
    st.markdown('<h1 class="main-header">Content Review</h1>', unsafe_allow_html=True)
    
    # Filters
    col1, col2 = st.columns(2)
    with col1:
        status_filter = st.selectbox("Filter by Status", ["pending_review", "All", "rejected"])
    with col2:
        sort_order = st.selectbox("Sort by", ["Newest First", "Oldest First"])
    
    # Query
    query = """
    SELECT 
        c.id,
        c.caption,
        c.hashtags,
        c.video_gdrive_link,
        c.video_gdrive_file_id,
        c.status,
        c.created_at,
        p.title as product_title,
        p.price as product_price
    FROM content c
    JOIN products p ON c.product_id = p.id
    WHERE 1=1
    """
    
    if status_filter != "All":
        query += f" AND c.status = '{status_filter}'"
    
    query += " ORDER BY c.created_at " + ("DESC" if sort_order == "Newest First" else "ASC")
    
    content_items = execute_query(query)
    
    if content_items and len(content_items) > 0:
        for item in content_items:
            with st.expander(f"{item['product_title']} - {item['created_at'].strftime('%Y-%m-%d %H:%M')}", expanded=True):
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    # Improved video preview with loading state
                    if item['video_gdrive_file_id']:
                        with st.spinner('Loading video...'):
                            try:
                                # Horizontal video embed (9:16 aspect ratio for vertical videos)
                                st.markdown(f"""
                                <div style="position: relative; width: 100%; max-width: 360px; margin: 0 auto;">
                                    <div style="position: relative; padding-bottom: 177.78%; height: 0; overflow: hidden; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                                        <iframe src="https://drive.google.com/file/d/{item['video_gdrive_file_id']}/preview" 
                                                style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: none;"
                                                allow="autoplay; encrypted-media" 
                                                allowfullscreen
                                                loading="lazy"></iframe>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                st.markdown("<br>", unsafe_allow_html=True)
                                
                                # Direct link button
                                if item['video_gdrive_link']:
                                    st.link_button("📂 Open in Google Drive", item['video_gdrive_link'], use_container_width=True)
                            except Exception as e:
                                st.error("Video preview unavailable")
                                if item['video_gdrive_link']:
                                    st.link_button("📂 Open Video in Drive", item['video_gdrive_link'], use_container_width=True)
                    else:
                        st.info("No video available")
                
                with col2:
                    # Edit caption
                    caption = st.text_area(
                        "Caption",
                        value=item['caption'],
                        key=f"caption_{item['id']}",
                        height=150
                    )
                    
                    # Edit hashtags
                    hashtags_str = " ".join(item['hashtags']) if item['hashtags'] else ""
                    hashtags = st.text_input(
                        "Hashtags",
                        value=hashtags_str,
                        key=f"hashtags_{item['id']}"
                    )
                    
                    # Platform selector
                    platforms = st.multiselect(
                        "Select Platforms",
                        ["TikTok", "Facebook", "YouTube"],
                        default=["TikTok"],
                        key=f"platforms_{item['id']}"
                    )
                
                # Action buttons
                col1, col2, col3 = st.columns([1, 1, 2])
                
                with col1:
                    if st.button("✅ Approve", key=f"approve_{item['id']}", use_container_width=True, type="primary"):
                        if send_approval_webhook(item['id'], "approve"):
                            st.success("Content approved successfully!")
                            logger.info(f"Content approved: {item['id']}")
                            st.rerun()
                
                with col2:
                    if st.button("❌ Reject", key=f"reject_{item['id']}", use_container_width=True):
                        st.session_state[f"show_reject_{item['id']}"] = True
                
                # Rejection modal
                if st.session_state.get(f"show_reject_{item['id']}", False):
                    reason = st.text_area("Rejection Reason", key=f"reason_{item['id']}")
                    if st.button("Confirm Reject", key=f"confirm_reject_{item['id']}"):
                        if send_approval_webhook(item['id'], "reject", reason):
                            st.success("Content rejected")
                            logger.info(f"Content rejected: {item['id']}")
                            st.session_state[f"show_reject_{item['id']}"] = False
                            st.rerun()
                
                st.markdown("---")
    else:
        st.info("No content pending review")

# PAGE 4: CONTENT CALENDAR
elif page == "Content Calendar":
    st.markdown('<h1 class="main-header">Content Calendar</h1>', unsafe_allow_html=True)
    
    # Date filters
    col1, col2 = st.columns(2)
    with col1:
        date_from = st.date_input("From", value=datetime.now() - timedelta(days=30))
    with col2:
        date_to = st.date_input("To", value=datetime.now())
    
    query = """
    SELECT 
        p.id,
        p.post_url,
        p.platform,
        p.published_at,
        c.caption,
        pr.title as product_title,
        COALESCE(a.views, 0) as views,
        COALESCE(a.likes, 0) as likes,
        COALESCE(a.comments, 0) as comments,
        COALESCE(a.engagement_rate, 0) as engagement_rate
    FROM posts p
    JOIN content c ON p.content_id = c.id
    JOIN products pr ON c.product_id = pr.id
    LEFT JOIN analytics a ON p.id = a.post_id
    WHERE p.published_at BETWEEN %s AND %s
    ORDER BY p.published_at DESC
    """
    
    posts = execute_query(query, (date_from, date_to))
    
    if posts and len(posts) > 0:
        for post in posts:
            with st.expander(f"{post['product_title']} - {post['published_at'].strftime('%Y-%m-%d %H:%M')}"):
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.write(f"**Platform:** {post['platform']}")
                    st.write(f"**Caption:** {post['caption'][:200]}...")
                    st.write(f"**Post URL:** [{post['post_url']}]({post['post_url']})")
                
                with col2:
                    st.metric("Views", f"{post['views']:,}")
                    st.metric("Likes", f"{post['likes']:,}")
                    st.metric("Engagement", f"{post['engagement_rate']:.2f}%")
    else:
        st.info("No posts in selected date range")

# PAGE 5: ANALYTICS DASHBOARD
elif page == "Analytics Dashboard":
    st.markdown('<h1 class="main-header">📈 Analytics Dashboard</h1>', unsafe_allow_html=True)
    
    # Date range selector
    col1, col2 = st.columns([1, 3])
    with col1:
        date_range = st.selectbox("Date Range", ["Last 7 Days", "Last 30 Days", "Last 90 Days", "All Time"])
    
    with col2:
        platform_filter = st.multiselect("Platforms", ["tiktok", "facebook", "youtube", "instagram"], default=["tiktok", "facebook", "youtube", "instagram"])
    
    # Calculate date range
    if date_range == "Last 7 Days":
        days = 7
    elif date_range == "Last 30 Days":
        days = 30
    elif date_range == "Last 90 Days":
        days = 90
    else:
        days = 36500  # All time
    
    date_filter = datetime.now() - timedelta(days=days)
    
    st.markdown("---")
    
    # SECTION 1: Real-Time Analytics from Upload-Post API
    st.subheader("📊 Real-Time Platform Analytics")
    
    api_key = os.getenv('UPLOAD_POST_API_KEY')
    profile = os.getenv('UPLOAD_POST_PROFILE', 'ipurchase')
    
    if api_key:
        try:
            # Fetch analytics from Upload-Post
            url = f"https://api.upload-post.com/api/analytics/{profile}"
            headers = {"Authorization": f"Apikey {api_key}"}
            params = {"platforms": ",".join(platform_filter)}
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            analytics = response.json()
            
            col1, col2, col3, col4 = st.columns(4)
            
            # TikTok
            if 'tiktok' in platform_filter and 'tiktok' in analytics:
                tiktok = analytics['tiktok']
                if not tiktok.get('success') == False:
                    with col1:
                        st.metric("TikTok Followers", f"{tiktok.get('followers', 0):,}")
                        st.metric("TikTok Views", f"{tiktok.get('reach', 0):,}")
                        st.caption(f"Impressions: {tiktok.get('impressions', 0):,}")
                        st.caption(f"Profile Views: {tiktok.get('profileViews', 0):,}")
            
            # Facebook
            if 'facebook' in platform_filter and 'facebook' in analytics:
                facebook = analytics['facebook']
                if not facebook.get('success') == False:
                    with col2:
                        st.metric("Facebook Followers", f"{facebook.get('followers', 0):,}")
                        st.metric("Facebook Views", f"{facebook.get('reach', 0):,}")
                        st.caption(f"Impressions: {facebook.get('impressions', 0):,}")
            
            # YouTube
            if 'youtube' in platform_filter and 'youtube' in analytics:
                youtube = analytics['youtube']
                if not youtube.get('success') == False:
                    with col3:
                        st.metric("YouTube Followers", f"{youtube.get('followers', 0):,}")
                        st.metric("YouTube Views", f"{youtube.get('reach', 0):,}")
                        st.caption(f"Impressions: {youtube.get('impressions', 0):,}")
            
            # Instagram
            if 'instagram' in platform_filter and 'instagram' in analytics:
                instagram = analytics['instagram']
                if not instagram.get('success') == False:
                    with col4:
                        st.metric("Instagram Followers", f"{instagram.get('followers', 0):,}")
                        st.metric("Instagram Views", f"{instagram.get('reach', 0):,}")
                        st.caption(f"Impressions: {instagram.get('impressions', 0):,}")
                        st.caption(f"Profile Views: {instagram.get('profileViews', 0):,}")
            
        except Exception as e:
            logger.error(f"Failed to fetch Upload-Post analytics: {str(e)}")
            st.error("Unable to fetch real-time analytics")
    
    st.markdown("---")
    
    # SECTION 2: Upload History from Upload-Post API
    st.subheader("📋 Recent Upload History")
    
    if api_key:
        try:
            # Fetch upload history
            history_url = "https://api.upload-post.com/api/uploadposts/history"
            headers = {"Authorization": f"Apikey {api_key}"}
            params = {"page": 1, "limit": 20}
            
            response = requests.get(history_url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            history_data = response.json()
            
            history_items = history_data.get('history', [])
            
            if history_items:
                # Filter by selected platforms
                filtered_history = [
                    item for item in history_items 
                    if item.get('platform') in platform_filter
                ]
                
                # Create DataFrame
                df_history = pd.DataFrame(filtered_history)
                
                # Display summary
                col1, col2, col3, col4 = st.columns(4)
                
                total_uploads = len(filtered_history)
                successful_uploads = len([item for item in filtered_history if item.get('success')])
                failed_uploads = total_uploads - successful_uploads
                success_rate = (successful_uploads / total_uploads * 100) if total_uploads > 0 else 0
                
                col1.metric("Total Uploads", total_uploads)
                col2.metric("Successful", successful_uploads)
                col3.metric("Failed", failed_uploads)
                col4.metric("Success Rate", f"{success_rate:.1f}%")
                
                st.markdown("---")
                
                # Display history table with video preview
                if not df_history.empty:
                    for idx, item in enumerate(filtered_history[:10]):  # Show top 10
                        with st.expander(f"📹 {item.get('post_title', 'Untitled')[:60]}... - {item.get('platform', 'Unknown').upper()}", expanded=False):
                            col1, col2 = st.columns([1, 2])
                            
                            with col1:
                                # Video preview if available
                                if item.get('prevalidation_metadata', {}).get('remote_public_url'):
                                    video_url = item['prevalidation_metadata']['remote_public_url']
                                    st.video(video_url)
                                elif item.get('post_url'):
                                    st.link_button("🔗 View Post", item['post_url'], use_container_width=True)
                                else:
                                    st.info("No video preview available")
                            
                            with col2:
                                st.write(f"**Platform:** {item.get('platform', 'Unknown').upper()}")
                                st.write(f"**Status:** {'✅ Success' if item.get('success') else '❌ Failed'}")
                                st.write(f"**Upload Time:** {item.get('upload_timestamp', 'N/A')}")
                                st.write(f"**Media Type:** {item.get('media_type', 'N/A')}")
                                
                                if item.get('post_url'):
                                    st.write(f"**Post URL:** [{item['post_url']}]({item['post_url']})")
                                
                                if item.get('error_message'):
                                    st.error(f"Error: {item['error_message']}")
                                
                                # Video metadata
                                if item.get('prevalidation_metadata'):
                                    meta = item['prevalidation_metadata']
                                    st.caption(f"Resolution: {meta.get('width', 'N/A')}x{meta.get('height', 'N/A')} | FPS: {meta.get('fps', 'N/A')} | Duration: {meta.get('duration', 'N/A')}s")
            else:
                st.info("No upload history found")
                
        except Exception as e:
            logger.error(f"Failed to fetch upload history: {str(e)}")
            st.error("Unable to fetch upload history")
    
    st.markdown("---")
    
    # SECTION 3: Database Analytics (Engagement from stored analytics)
    st.subheader("💬 Engagement Analytics (Database)")
    
    # Summary metrics from database
    metrics_query = """
    SELECT 
        SUM(a.views) as total_views,
        SUM(a.likes + a.comments + a.shares) as total_engagement,
        AVG(a.engagement_rate) as avg_engagement_rate,
        SUM(a.likes) as total_likes,
        SUM(a.comments) as total_comments,
        SUM(a.shares) as total_shares,
        COUNT(DISTINCT p.id) as total_posts
    FROM analytics a
    JOIN posts p ON a.post_id = p.id
    WHERE p.published_at >= %s
    AND p.platform = ANY(%s)
    """
    
    metrics = execute_query(metrics_query, (date_filter, platform_filter))
    
    if metrics and metrics[0]:
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Total Views", f"{int(metrics[0]['total_views'] or 0):,}")
        with col2:
            st.metric("Total Likes", f"{int(metrics[0]['total_likes'] or 0):,}")
        with col3:
            st.metric("Total Comments", f"{int(metrics[0]['total_comments'] or 0):,}")
        with col4:
            st.metric("Total Shares", f"{int(metrics[0]['total_shares'] or 0):,}")
        with col5:
            st.metric("Avg Engagement Rate", f"{float(metrics[0]['avg_engagement_rate'] or 0):.2f}%")
    
    st.markdown("---")
    
    # Engagement by platform chart (from database)
    engagement_query = """
    SELECT 
        p.platform,
        SUM(a.views) as views,
        SUM(a.likes) as likes,
        SUM(a.comments) as comments,
        SUM(a.shares) as shares
    FROM analytics a
    JOIN posts p ON a.post_id = p.id
    WHERE p.published_at >= %s
    AND p.platform = ANY(%s)
    GROUP BY p.platform
    """
    
    engagement_data = execute_query(engagement_query, (date_filter, platform_filter))
    
    if engagement_data and len(engagement_data) > 0:
        df_engagement = pd.DataFrame(engagement_data)
        
        fig = go.Figure(data=[
            go.Bar(name='Views', x=df_engagement['platform'], y=df_engagement['views']),
            go.Bar(name='Likes', x=df_engagement['platform'], y=df_engagement['likes']),
            go.Bar(name='Comments', x=df_engagement['platform'], y=df_engagement['comments']),
            go.Bar(name='Shares', x=df_engagement['platform'], y=df_engagement['shares'])
        ])
        fig.update_layout(barmode='stack', title='Engagement Breakdown by Platform')
        st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # Top performing posts (from database)
    st.subheader("🏆 Top 10 Performing Posts")
    
    top_posts_query = """
    SELECT 
        pr.title,
        p.platform,
        p.post_url,
        COALESCE(a.views, 0) as views,
        COALESCE(a.likes, 0) as likes,
        COALESCE(a.comments, 0) as comments,
        COALESCE(a.shares, 0) as shares,
        COALESCE(a.engagement_rate, 0) as engagement_rate,
        p.published_at
    FROM posts p
    JOIN content c ON p.content_id = c.id
    JOIN products pr ON c.product_id = pr.id
    LEFT JOIN analytics a ON p.id = a.post_id
    WHERE p.published_at >= %s
    AND p.platform = ANY(%s)
    AND p.status = 'published'
    ORDER BY (COALESCE(a.views, 0) + COALESCE(a.likes, 0) + COALESCE(a.comments, 0) + COALESCE(a.shares, 0)) DESC
    LIMIT 10
    """
    
    top_posts = execute_query(top_posts_query, (date_filter, platform_filter))
    
    if top_posts and len(top_posts) > 0:
        for i, post in enumerate(top_posts, 1):
            col1, col2, col3, col4, col5 = st.columns([4, 1, 1, 1, 2])
            with col1:
                st.write(f"**{i}. {post['title']}** ({post['platform']})")
                st.caption(f"Published: {post['published_at'].strftime('%Y-%m-%d %H:%M')}")
            with col2:
                st.metric("Views", post['views'])
            with col3:
                st.metric("Likes", post['likes'])
            with col4:
                st.metric("Comments", post['comments'])
            with col5:
                st.metric("Engagement", f"{post['engagement_rate']:.2f}%")
                if post['post_url']:
                    st.link_button("View", post['post_url'], use_container_width=True)
            st.markdown("---")
    else:
        st.info("No analytics data available for selected date range")

# PAGE 6: SETTINGS
elif page == "Settings":
    st.markdown('<h1 class="main-header">Settings</h1>', unsafe_allow_html=True)
    
    # Brand Voice
    st.subheader("Brand Voice")
    
    brand_voice_query = """
    SELECT * FROM brand_voice 
    WHERE is_active = true 
    ORDER BY created_at DESC 
    LIMIT 1
    """
    
    brand_voice = execute_query(brand_voice_query)
    
    if brand_voice and len(brand_voice) > 0:
        voice = brand_voice[0]
        st.write(f"**Tone:** {voice['tone_description']}")
        st.write(f"**Emoji Usage:** {voice['emoji_usage']}")
        
        with st.expander("Sample Captions"):
            if voice['sample_captions']:
                for i, caption in enumerate(voice['sample_captions'], 1):
                    st.write(f"{i}. {caption}")
    else:
        st.info("No brand voice configured")
    
    if st.button("Re-analyze Brand Voice"):
        st.info("Trigger n8n Brand Voice Analysis workflow manually")
    
    st.markdown("---")
    
    # API Configuration
    st.subheader("API Configuration")
    
    st.text_input("n8n Webhook URL", value=os.getenv('N8N_WEBHOOK_URL', ''), disabled=True)
    st.text_input("Upload-Post Profile", value=os.getenv('UPLOAD_POST_PROFILE', ''), disabled=True)
    
    st.markdown("---")
    
    # Database Statistics
    st.subheader("Database Statistics")
    
    stats_query = """
    SELECT 
        (SELECT COUNT(*) FROM products) as products,
        (SELECT COUNT(*) FROM content) as content,
        (SELECT COUNT(*) FROM posts) as posts,
        (SELECT COUNT(*) FROM analytics) as analytics
    """
    
    stats = execute_query(stats_query)
    
    if stats:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Products", stats[0]['products'])
        col2.metric("Content", stats[0]['content'])
        col3.metric("Posts", stats[0]['posts'])
        col4.metric("Analytics", stats[0]['analytics'])


# Footer
st.markdown("---")
st.caption(f"TikTok Marketing Automation System | Logged in as: {st.session_state.username}")
