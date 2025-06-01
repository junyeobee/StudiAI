/**
 * JS_ARROW_01 테스트용 - 화살표 함수들
 */

// 간단한 화살표 함수
const simpleArrow = () => {
    return "simple arrow result";
};

// 매개변수가 있는 화살표 함수
const addNumbers = (a, b) => a + b;

// 비동기 화살표 함수
const asyncArrow = async (url) => {
    const response = await fetch(url);
    return response.json();
};

// 중첩된 화살표 함수
const nestedArrow = () => {
    const innerArrow = (x) => x * 2;
    return innerArrow;
};

// 일반 함수도 포함
function regularFunction() {
    return "regular function";
} 