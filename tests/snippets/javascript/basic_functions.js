/**
 * JS_BASIC_01 테스트용 - 기본 JavaScript 함수들
 */
const axios = require('axios');

function foo(x) {
    // 간단한 함수
    return x * 2;
}

function bar(name, age = 25) {
    // 매개변수가 있는 함수
    return `Hello ${name}, you are ${age} years old`;
}

function processArray(items) {
    // 배열 처리 함수
    return items.map(item => item.toUpperCase());
}

async function fetchUserData(userId) {
    // 비동기 함수
    const response = await axios.get(`/users/${userId}`);
    return response.data;
} 