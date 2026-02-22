# Backend Integration Guide

This document outlines all the places in the frontend where backend API integration is required.

## Overview

The frontend is fully functional with mock data. All backend integration points are marked with `// TODO: Backend API call placeholder` comments in the code.

## API Endpoints Needed

### 1. User Authentication

#### POST `/api/signup`
**Location:** `signup.html` (line ~250)

**Request:**
```json
{
  "name": "John Doe",
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Expected Response:**
```json
{
  "token": "jwt-auth-token-here",
  "user": {
    "id": "user-id",
    "name": "John Doe",
    "email": "user@example.com"
  }
}
```

**Frontend Storage:**
- `localStorage.setItem('authToken', data.token)`
- `localStorage.setItem('currentUser', JSON.stringify(data.user))`

---

#### POST `/api/login`
**Location:** `login.html` (line ~180)

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Expected Response:**
```json
{
  "token": "jwt-auth-token-here",
  "user": {
    "id": "user-id",
    "name": "John Doe",
    "email": "user@example.com"
  }
}
```

**Frontend Storage:**
- `localStorage.setItem('authToken', data.token)`
- `localStorage.setItem('currentUser', JSON.stringify(data.user))`

---

### 2. Course Roadmap Generation

#### POST `/api/get-course-roadmap`
**Location:** `index.html` (line ~240)

**Request:**
```json
{
  "university": "ucl",
  "course": "Computer Science" // or UCAS code like "G400"
}
```

**Request Headers:**
```javascript
{
  'Content-Type': 'application/json',
  'Authorization': 'Bearer ' + localStorage.getItem('authToken')
}
```

**Expected Response:**
```json
{
  "courseName": "Computer Science BSc",
  "modules": [
    "Introduction to Computer Science",
    "Programming Fundamentals",
    "Data Structures",
    "Algorithms",
    "Software Engineering",
    "Databases",
    "Operating Systems",
    "Final Year Project"
  ],
  "moduleDetails": {
    "Introduction to Computer Science": {
      "description": "This module introduces fundamental concepts...",
      "credits": 15,
      "level": 1
    },
    // ... other modules
  }
}
```

**Frontend Usage:**
The frontend will:
1. Join modules array into comma-separated string
2. Redirect to `roadmap.html?input={modules}&course={courseName}&university={university}`

---

## Current Mock Behavior

### Authentication (login/signup)
- Currently stores user data in `localStorage` without validation
- Any email/password combination is accepted
- Mock user object is created with email and name

### Roadmap Generation
- Currently creates a mock roadmap based on user input
- Modules: `{courseName}, Introduction to {courseName}, Core Concepts, Advanced Topics, Practical Applications, Research Methods, Final Project`
- No actual UCAS code lookup or database query

---

## Frontend Data Storage

The frontend uses `localStorage` to persist user sessions:

### Keys Used:
1. **`currentUser`**: JSON string containing user object
   ```json
   {
     "id": "user-id",
     "name": "John Doe",
     "email": "user@example.com"
   }
   ```

2. **`authToken`**: JWT token for authenticated requests
   ```
   "jwt-token-string-here"
   ```

### Accessing User Data:
```javascript
const user = JSON.parse(localStorage.getItem('currentUser'));
const token = localStorage.getItem('authToken');
```

### Logout:
```javascript
localStorage.removeItem('currentUser');
localStorage.removeItem('authToken');
```

---

## Security Considerations

When implementing the backend:

1. **Password Hashing**: Never store passwords in plain text
2. **JWT Tokens**: Use secure, expiring tokens
3. **CORS**: Configure appropriate CORS headers
4. **Input Validation**: Validate and sanitize all inputs
5. **Rate Limiting**: Implement rate limiting on authentication endpoints
6. **HTTPS**: Ensure all API calls use HTTPS in production

---

## Integration Steps

1. **Set up your backend server** with the endpoints listed above
2. **Update the frontend JavaScript** files:
   - Uncomment the backend API calls (marked with `// Example API call`)
   - Remove or comment out the mock implementations
   - Update the API endpoint URLs to match your backend

3. **Test the integration**:
   - Test signup flow
   - Test login flow
   - Test roadmap generation with UCAS codes
   - Test with invalid inputs to ensure error handling works

4. **Error Handling**: The frontend expects error responses in this format:
   ```json
   {
     "message": "Error description here"
   }
   ```

---

## Files Modified

- `frontend/index.html` - Course/university selection and roadmap generation
- `frontend/login.html` - User login
- `frontend/signup.html` - User registration
- `frontend/roadmap.html` - Displays the generated roadmap (receives data via URL params)

---

## Contact

For questions about frontend integration, check the code comments or consult with the frontend developer.
