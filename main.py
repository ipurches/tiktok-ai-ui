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
from urllib.parse import quote_plus
import logging

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
</style>
""", unsafe_allow_html=True)

def get_db_connection():
    """Create database connection"""
    try:
        host = os.getenv('DB_HOST')
        port = os.getenv('DB_PORT', '5432')
        database = os.getenv('DB_NAME', 'postgres')
        user = os.getenv('DB_USER')
        password = os.getenv('DB_PASSWORD')
        
        logger.info(f"Connecting to: {user}@{host}:{port}/{database}")
        
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
        
        logger.info("Database connection established successfully")
        return conn
        
    except Exception as e:
        logger.error(f"Connection failed: {str(e)}")
        st.error(f"Database connection failed: {str(e)}")
        return None
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
                conn.close()
                return result
            else:
                conn.commit()
                logger.info("Query executed successfully, changes committed")
                conn.close()
                return True
                
    except Exception as e:
        logger.error(f"Query execution failed: {str(e)}")
        if conn and not conn.closed:
            try:
                conn.rollback()
                conn.close()
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
    profile = os.getenv('UPLOAD_POST_PROFILE', 'sajjad_ai')
    
    if not api_key or api_key == 'your_upload_post_api_key_here':
        logger.warning("Upload-Post API key not configured")
        return None
    
    try:
        url = f"https://api.upload-post.com/api/analytics/{profile}"
        headers = {"Authorization": f"Apikey {api_key}"}
        params = {"platforms": "facebook,instagram,tiktok"}
        
        logger.info(f"Fetching analytics for profile: {profile}")
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        logger.info("Analytics fetched successfully")
        return response.json()
    except Exception as e:
        logger.error(f"Failed to fetch analytics: {str(e)}")
        return None

# Sidebar navigation
st.sidebar.title("Navigation")
page = st.sidebar.radio(
    "Go to",
    ["Dashboard Overview", "Product Management", "Content Review", 
     "Content Calendar", "Analytics Dashboard", "Settings"]
)

# Quick stats in sidebar
st.sidebar.markdown("---")
st.sidebar.subheader("Quick Stats")

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
    st.markdown('<h1 class="main-header">Dashboard Overview</h1>', unsafe_allow_html=True)
    
    # Top metrics
    metrics_query = """
    SELECT 
        (SELECT COUNT(*) FROM products) as total_products,
        (SELECT COUNT(*) FROM content WHERE status = 'pending_review') as pending_review,
        (SELECT COUNT(*) FROM posts WHERE status = 'published') as published_posts,
        (SELECT COALESCE(SUM(views), 0) FROM analytics) as total_views
    """
    
    metrics = execute_query(metrics_query)
    
    if metrics:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <p class="metric-value">{metrics[0]['total_products']}</p>
                <p class="metric-label">Total Products</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <p class="metric-value">{metrics[0]['pending_review']}</p>
                <p class="metric-label">Pending Review</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
            <div class="metric-card">
                <p class="metric-value">{metrics[0]['published_posts']}</p>
                <p class="metric-label">Published Posts</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            st.markdown(f"""
            <div class="metric-card">
                <p class="metric-value">{metrics[0]['total_views']:,}</p>
                <p class="metric-label">Total Views</p>
            </div>
            """, unsafe_allow_html=True)
    
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
                    st.write(f"{post['platform']} | {post['published_at'].strftime('%Y-%m-%d %H:%M')}")
                st.markdown("---")
    else:
        st.info("No published posts yet. Start by approving content!")
    
    # Quick actions
    st.subheader("Quick Actions")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("Go to Content Review", use_container_width=True):
            st.session_state.page = "Content Review"
            st.rerun()
    
    with col2:
        if st.button("Go to Product Management", use_container_width=True):
            st.session_state.page = "Product Management"
            st.rerun()
    
    with col3:
        if st.button("Go to Analytics", use_container_width=True):
            st.session_state.page = "Analytics Dashboard"
            st.rerun()

# PAGE 2: PRODUCT MANAGEMENT
elif page == "Product Management":
    st.markdown('<h1 class="main-header">Product Management</h1>', unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["Upload Product", "View Products"])
    
    with tab1:
        st.subheader("Add New Product")
        
        with st.form("product_form"):
            title = st.text_input("Product Title", placeholder="e.g., Premium Leather Wallet")
            price = st.number_input("Price", min_value=0.0, step=0.01, format="%.2f")
            category = st.selectbox("Category", ["Accessories", "Electronics", "Clothing", "Home", "Other"])
            description = st.text_area("Description", placeholder="Detailed product description...")
            source = st.selectbox("Source", ["shopify", "tiktok_shop", "manual"])
            product_id = st.text_input("Product ID", placeholder="unique-product-id")
            image_file = st.file_uploader("Product Image", type=["jpg", "jpeg", "png"])
            
            submitted = st.form_submit_button("Add Product", use_container_width=True)
            
            if submitted:
                if not title or not product_id:
                    st.error("Title and Product ID are required")
                else:
                    # Placeholder for image upload logic
                    image_url = "placeholder_image_url" if image_file else None
                    
                    insert_query = """
                    INSERT INTO products (source, product_id, title, description, price, category, images, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending_content_generation')
                    """
                    
                    images_json = f'["{image_url}"]' if image_url else '[]'
                    
                    result = execute_query(
                        insert_query,
                        (source, product_id, title, description, price, category, images_json),
                        fetch=False
                    )
                    
                    if result:
                        logger.info(f"Product added successfully: {product_id}")
                        st.success("Product added successfully!")
                        st.balloons()
                    else:
                        st.error("Failed to add product")
    
    with tab2:
        st.subheader("Product List")
        
        # Filters
        col1, col2, col3 = st.columns(3)
        with col1:
            filter_source = st.selectbox("Filter by Source", ["All", "shopify", "tiktok_shop", "manual"])
        with col2:
            filter_status = st.selectbox("Filter by Status", ["All", "pending_content_generation", "content_generated", "published"])
        with col3:
            search_term = st.text_input("Search", placeholder="Search by title...")
        
        # Build query
        query = "SELECT * FROM products WHERE 1=1"
        params = []
        
        if filter_source != "All":
            query += " AND source = %s"
            params.append(filter_source)
        
        if filter_status != "All":
            query += " AND status = %s"
            params.append(filter_status)
        
        if search_term:
            query += " AND title ILIKE %s"
            params.append(f"%{search_term}%")
        
        query += " ORDER BY created_at DESC LIMIT 50"
        
        products = execute_query(query, params if params else None)
        
        if products and len(products) > 0:
            # Convert to DataFrame
            df = pd.DataFrame(products)
            df['price'] = df['price'].apply(lambda x: f"${float(x):.2f}")
            df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
            
            st.dataframe(
                df[['title', 'price', 'category', 'source', 'status', 'created_at']],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No products found")

# PAGE 3: CONTENT REVIEW
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
                    # Video preview
                    if item['video_gdrive_file_id']:
                        st.markdown(f"""
                        <iframe src="https://drive.google.com/file/d/{item['video_gdrive_file_id']}/preview" 
                                width="100%" height="300" frameborder="0" allowfullscreen></iframe>
                        """, unsafe_allow_html=True)
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
                        ["TikTok", "Instagram", "Facebook", "LinkedIn"],
                        default=["Facebook"],
                        key=f"platforms_{item['id']}"
                    )
                
                # Action buttons
                col1, col2, col3 = st.columns([1, 1, 2])
                
                with col1:
                    if st.button("Approve", key=f"approve_{item['id']}", use_container_width=True, type="primary"):
                        if send_approval_webhook(item['id'], "approve"):
                            st.success("Content approved successfully!")
                            logger.info(f"Content approved: {item['id']}")
                            st.rerun()
                
                with col2:
                    if st.button("Reject", key=f"reject_{item['id']}", use_container_width=True):
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
    st.markdown('<h1 class="main-header">Analytics Dashboard</h1>', unsafe_allow_html=True)
    
    # Date range selector
    col1, col2 = st.columns([1, 3])
    with col1:
        date_range = st.selectbox("Date Range", ["Last 7 Days", "Last 30 Days", "Last 90 Days", "All Time"])
    
    with col2:
        platform_filter = st.multiselect("Platforms", ["facebook", "instagram", "tiktok"], default=["facebook"])
    
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
    
    # Summary metrics
    metrics_query = """
    SELECT 
        SUM(a.views) as total_views,
        SUM(a.likes + a.comments + a.shares) as total_engagement,
        AVG(a.engagement_rate) as avg_engagement_rate,
        COUNT(DISTINCT p.id) as total_posts
    FROM analytics a
    JOIN posts p ON a.post_id = p.id
    WHERE p.published_at >= %s
    AND p.platform = ANY(%s)
    """
    
    metrics = execute_query(metrics_query, (date_filter, platform_filter))
    
    if metrics and metrics[0]:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Views", f"{int(metrics[0]['total_views'] or 0):,}")
        with col2:
            st.metric("Total Engagement", f"{int(metrics[0]['total_engagement'] or 0):,}")
        with col3:
            st.metric("Avg Engagement Rate", f"{float(metrics[0]['avg_engagement_rate'] or 0):.2f}%")
        with col4:
            st.metric("Total Posts", f"{int(metrics[0]['total_posts'] or 0):,}")
    
    st.markdown("---")
    
    # Views over time chart
    chart_query = """
    SELECT 
        DATE(p.published_at) as date,
        p.platform,
        SUM(a.views) as total_views
    FROM analytics a
    JOIN posts p ON a.post_id = p.id
    WHERE p.published_at >= %s
    AND p.platform = ANY(%s)
    GROUP BY DATE(p.published_at), p.platform
    ORDER BY date
    """
    
    chart_data = execute_query(chart_query, (date_filter, platform_filter))
    
    if chart_data and len(chart_data) > 0:
        df = pd.DataFrame(chart_data)
        fig = px.line(df, x='date', y='total_views', color='platform',
                     title='Views Over Time',
                     labels={'total_views': 'Views', 'date': 'Date'})
        st.plotly_chart(fig, use_container_width=True)
        
        # Engagement by platform
        engagement_query = """
        SELECT 
            p.platform,
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
            
            fig2 = go.Figure(data=[
                go.Bar(name='Likes', x=df_engagement['platform'], y=df_engagement['likes']),
                go.Bar(name='Comments', x=df_engagement['platform'], y=df_engagement['comments']),
                go.Bar(name='Shares', x=df_engagement['platform'], y=df_engagement['shares'])
            ])
            fig2.update_layout(barmode='stack', title='Engagement by Platform')
            st.plotly_chart(fig2, use_container_width=True)
    
    # Top performing posts
    st.subheader("Top 5 Performing Posts")
    
    top_posts_query = """
    SELECT 
        pr.title,
        p.platform,
        a.views,
        a.engagement_rate,
        p.post_url
    FROM analytics a
    JOIN posts p ON a.post_id = p.id
    JOIN content c ON p.content_id = c.id
    JOIN products pr ON c.product_id = pr.id
    WHERE p.published_at >= %s
    AND p.platform = ANY(%s)
    ORDER BY a.views DESC
    LIMIT 5
    """
    
    top_posts = execute_query(top_posts_query, (date_filter, platform_filter))
    
    if top_posts and len(top_posts) > 0:
        for i, post in enumerate(top_posts, 1):
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.write(f"**{i}. {post['title']}** ({post['platform']})")
            with col2:
                st.write(f"{post['views']:,} views")
            with col3:
                st.write(f"{post['engagement_rate']:.2f}% engagement")
    else:
        st.info("No analytics data available")

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
st.caption("TikTok Marketing Automation System | Version 1.0.0")