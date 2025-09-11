# 🧪 Live User Testing Guide

This guide shows you how to test the enhanced multi-agent system with real user interactions.

## 🚀 Quick Start

### 1. Start the Backend Server
```bash
cd backend
python start_server.py
```

The server will start on `http://localhost:8000`

### 2. Run Live User Test
```bash
# In a new terminal
cd backend
python test_live_user.py
```

## 🎯 What the Live Test Does

### **Conversation Flow**
1. **First Conversation**: User starts with stress and sleep issues
2. **Follow-up Messages**: User continues the conversation
3. **Second Conversation**: User starts a new conversation (tests cumulative context)
4. **Status Management**: Tests conversation status transitions
5. **API Testing**: Verifies all endpoints work correctly

### **Features Tested**
- ✅ **Personalized Greetings**: AI remembers previous conversations
- ✅ **Cumulative Context**: Each conversation builds on previous ones
- ✅ **Status Management**: Conversations transition between active/in-progress/archived
- ✅ **HIPAA Compliance**: Responses maintain privacy standards
- ✅ **Multi-Agent Coordination**: All three agents work together

## 🔍 Manual Testing

### **API Endpoints You Can Test**

#### 1. Start a New Conversation
```bash
curl -X POST "http://localhost:8000/api/ai/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id": null,
    "message": "Hi, I need help with my anxiety"
  }'
```

#### 2. Continue a Conversation
```bash
curl -X POST "http://localhost:8000/api/ai/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id": "YOUR_CONVERSATION_ID",
    "message": "I tried the breathing exercises you suggested"
  }'
```

#### 3. Check Conversation Status
```bash
curl -X GET "http://localhost:8000/api/conversations/status/active"
```

#### 4. Get Conversation Details
```bash
curl -X GET "http://localhost:8000/api/conversations/YOUR_CONVERSATION_ID"
```

## 🎭 Expected Behavior

### **First Conversation**
- AI greets user warmly
- Provides supportive response about stress and sleep
- References techniques and offers help
- Conversation status: `active` → `in-progress`

### **Second Conversation (Same User)**
- AI greets user personally, referencing previous conversation
- Shows continuity of care
- Builds on previous context
- Demonstrates cumulative learning

### **Status Transitions**
- New conversation: `active`
- Ongoing conversation: `in-progress`
- Inactive conversation (15+ min): `archived`

## 🐛 Troubleshooting

### **Common Issues**

1. **Server won't start**
   - Check if port 8000 is available
   - Verify database connection
   - Check Azure OpenAI credentials

2. **Database errors**
   - Run the migration script first
   - Ensure PostgreSQL is running
   - Check database URL configuration

3. **API errors**
   - Verify server is running on localhost:8000
   - Check request format
   - Look at server logs for details

### **Debug Mode**
```bash
# Start server with debug logging
python start_server.py
```

## 📊 Monitoring

### **Check Server Health**
```bash
curl http://localhost:8000/health
```

### **View API Documentation**
Open `http://localhost:8000/docs` in your browser

### **Check Logs**
The server will show detailed logs of:
- User interactions
- AI agent responses
- Database operations
- Status transitions

## 🎉 Success Indicators

You'll know the system is working correctly when:

1. **Personalized Responses**: AI greets you by referencing previous conversations
2. **Context Continuity**: AI remembers what you discussed before
3. **Status Updates**: Conversations show correct status transitions
4. **Cumulative Learning**: Each conversation builds on previous ones
5. **HIPAA Compliance**: Responses focus on emotional patterns, not personal details

## 🔄 Testing Different Scenarios

### **Scenario 1: New User**
- Start fresh conversation
- Should get standard greeting
- No previous context

### **Scenario 2: Returning User**
- Start conversation after previous ones
- Should get personalized greeting
- Should reference previous conversations

### **Scenario 3: Multiple Conversations**
- Create several conversations
- Test cumulative context
- Verify status management

### **Scenario 4: Long Conversations**
- Have extended conversations
- Test summarization
- Verify context retention

## 📝 Notes

- The system uses a fixed user ID for testing: `d481d3de-3247-4fdc-a3de-12c98494cd9c`
- All conversations are associated with this test user
- The system maintains conversation history across sessions
- Status transitions happen automatically based on activity
