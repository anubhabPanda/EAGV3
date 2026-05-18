// Configuration
const API_BASE_URL = 'http://localhost:8000';

// State
let conversationHistory = [];
let availableTools = [];

// DOM Elements
const chatMessages = document.getElementById('chatMessages');
const chatInput = document.getElementById('chatInput');
const sendBtn = document.getElementById('sendBtn');
const sendBtnText = document.getElementById('sendBtnText');
const sendBtnLoading = document.getElementById('sendBtnLoading');
const resetBtn = document.getElementById('resetBtn');
const viewToolsBtn = document.getElementById('viewToolsBtn');
const rightPanelContent = document.getElementById('rightPanelContent');
const panelTitle = document.getElementById('panelTitle');
const toolsModal = document.getElementById('toolsModal');
const toolsList = document.getElementById('toolsList');

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    console.log('Initializing AI Agent UI...');
    
    // Load available tools
    await loadTools();
    
    // Event listeners
    sendBtn.addEventListener('click', sendMessage);
    resetBtn.addEventListener('click', resetConversation);
    viewToolsBtn.addEventListener('click', showToolsModal);
    
    // Modal close
    document.querySelector('.modal-close').addEventListener('click', hideToolsModal);
    toolsModal.addEventListener('click', (e) => {
        if (e.target === toolsModal) hideToolsModal();
    });
    
    // Chat input
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    
    // Focus input
    chatInput.focus();
});

// Load available tools
async function loadTools() {
    try {
        const response = await fetch(`${API_BASE_URL}/tools`);
        const data = await response.json();
        availableTools = data.tools || [];
        console.log('Loaded tools:', availableTools);
        
        // Update tools list in modal
        if (availableTools.length > 0) {
            toolsList.innerHTML = availableTools.map(tool => `
                <div class="tool-item">
                    <div class="tool-item-name">🛠️ ${tool.name}</div>
                    <div class="tool-item-desc">${tool.description || 'No description'}</div>
                </div>
            `).join('');
        } else {
            toolsList.innerHTML = '<p>No tools available</p>';
        }
    } catch (error) {
        console.error('Failed to load tools:', error);
        toolsList.innerHTML = '<p style="color: var(--danger)">Failed to load tools</p>';
    }
}

// Send message
async function sendMessage() {
    const message = chatInput.value.trim();
    if (!message) return;
    
    // Add user message to chat
    addMessage('user', message);
    
    // Clear input
    chatInput.value = '';
    chatInput.style.height = 'auto';
    
    // Show loading state
    setLoading(true);
    
    try {
        // Send to API
        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ message }),
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Agent response:', data);
        
        // Show thinking process if tools were called
        if (data.tool_calls && data.tool_calls.length > 0) {
            addThinkingMessage(data.tool_calls, data.iterations);
        }
        
        // Show agent response
        if (data.text) {
            addMessage('agent', data.text);
        }
        
        // Update right panel
        updateRightPanel(data);
        
    } catch (error) {
        console.error('Error sending message:', error);
        addMessage('system', `❌ Error: ${error.message}`);
    } finally {
        setLoading(false);
        chatInput.focus();
    }
}

// Add message to chat
function addMessage(role, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    
    if (role === 'user') {
        contentDiv.innerHTML = `<strong>You:</strong> ${escapeHtml(content)}`;
    } else if (role === 'agent') {
        contentDiv.innerHTML = `<strong>Agent:</strong> ${formatResponse(content)}`;
    } else if (role === 'system') {
        contentDiv.innerHTML = content;
    }
    
    messageDiv.appendChild(contentDiv);
    chatMessages.appendChild(messageDiv);
    
    // Scroll to bottom
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Add thinking message with tool calls
function addThinkingMessage(toolCalls, iterations) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message thinking';
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    
    let html = `<strong>🤔 Agent Thinking Process</strong> (${iterations} iteration${iterations > 1 ? 's' : ''})`;
    html += '<div class="thinking-steps">';
    
    toolCalls.forEach((call, index) => {
        const toolIcon = getToolIcon(call.tool);
        html += `
            <div class="tool-call">
                <div class="tool-call-header">
                    <span class="tool-name">${toolIcon} ${call.tool}</span>
                    <span class="tool-badge">Step ${index + 1}</span>
                </div>
                <div class="tool-args">
                    <strong>Arguments:</strong> ${JSON.stringify(call.arguments, null, 2)}
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    contentDiv.innerHTML = html;
    messageDiv.appendChild(contentDiv);
    chatMessages.appendChild(messageDiv);
    
    // Scroll to bottom
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Update right panel
function updateRightPanel(data) {
    // Check if dashboard HTML is present
    const hasDashboard = data.dashboard_html && data.dashboard_html.length > 0;

    console.log('Updating right panel:', {
        tool_calls: data.tool_calls,
        hasDashboard: hasDashboard,
        text_length: data.text ? data.text.length : 0
    });

    // If dashboard HTML is present, show it in an iframe
    if (hasDashboard) {
        panelTitle.textContent = '📊 Dashboard';

        // Create blob URL for the dashboard HTML
        const blob = new Blob([data.dashboard_html], { type: 'text/html' });
        const blobUrl = URL.createObjectURL(blob);

        rightPanelContent.innerHTML = `
            <div class="response-content" style="height: 100%; display: flex; flex-direction: column;">
                ${data.text ? `<div style="padding: 1rem; border-bottom: 1px solid var(--border-color);">${formatResponse(data.text)}</div>` : ''}
                <iframe
                    src="${blobUrl}"
                    style="flex: 1; width: 100%; border: none; min-height: 600px;"
                    sandbox="allow-scripts allow-same-origin allow-forms"
                ></iframe>
            </div>
        `;

        console.log('Dashboard iframe loaded from blob URL');
    }
    // Otherwise show the agent's response
    else if (data.text) {
        panelTitle.textContent = '💬 Agent Response';
        rightPanelContent.innerHTML = `
            <div class="response-content">
                ${formatResponse(data.text)}
            </div>
        `;
    }
}



// Format response (markdown-like)
function formatResponse(text) {
    // Escape HTML first
    text = escapeHtml(text);
    
    // Convert markdown-like formatting
    // Bold
    text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    
    // Italic
    text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');
    
    // Code blocks
    text = text.replace(/```(.+?)```/gs, '<pre><code>$1</code></pre>');
    
    // Inline code
    text = text.replace(/`(.+?)`/g, '<code>$1</code>');
    
    // Line breaks
    text = text.replace(/\n/g, '<br>');
    
    return text;
}

// Get tool icon
function getToolIcon(toolName) {
    const icons = {
        'search_web': '🔍',
        'read_file': '📖',
        'write_file': '✍️',
        'get_weather_info': '🌤️',
        'get_satellite_map': '🛰️',
        'dashboard': '📊',
    };
    return icons[toolName] || '🛠️';
}

// Escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Set loading state
function setLoading(loading) {
    if (loading) {
        sendBtn.disabled = true;
        sendBtn.classList.add('loading');
        sendBtnText.classList.add('hidden');
        sendBtnLoading.classList.remove('hidden');
        chatInput.disabled = true;
    } else {
        sendBtn.disabled = false;
        sendBtn.classList.remove('loading');
        sendBtnText.classList.remove('hidden');
        sendBtnLoading.classList.add('hidden');
        chatInput.disabled = false;
    }
}

// Reset conversation
async function resetConversation() {
    if (!confirm('Are you sure you want to reset the conversation?')) return;
    
    try {
        await fetch(`${API_BASE_URL}/reset`, { method: 'POST' });
        
        // Clear UI
        chatMessages.innerHTML = `
            <div class="message system">
                <div class="message-content">
                    <strong>System:</strong> Conversation reset. How can I help you?
                </div>
            </div>
        `;
        
        rightPanelContent.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">🎯</div>
                <h3>Ready to assist!</h3>
                <p>Send a message to see my response and tool usage here.</p>
            </div>
        `;
        
        panelTitle.textContent = '💬 Response';
        conversationHistory = [];
        
    } catch (error) {
        console.error('Failed to reset:', error);
        alert('Failed to reset conversation');
    }
}

// Show tools modal
function showToolsModal() {
    toolsModal.classList.remove('hidden');
}

// Hide tools modal
function hideToolsModal() {
    toolsModal.classList.add('hidden');
}
