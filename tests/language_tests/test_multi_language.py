import asyncio
import logging
import sys
from pathlib import Path

# 프로젝트 루트 디렉터리를 Python 경로에 추가
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent  # tests/language_tests/ -> tests/ -> 루트
sys.path.insert(0, str(project_root))

from app.services.extract_for_file_service import extract_functions_by_type, get_supported_file_types

# 로그 레벨 설정
logging.getLogger('api').setLevel(logging.INFO)

async def test_multi_language_support():
    """다중 언어 함수 추출 테스트"""
    
    print("🌍 다중 언어 함수 추출 테스트")
    print("=" * 80)
    
    # 지원하는 파일 타입 확인
    supported_types = get_supported_file_types()
    print(f"📋 지원하는 파일 타입: {supported_types}")
    print()
    
    # 각 언어별 테스트
    await test_java_extraction()
    print()
    await test_cpp_extraction()
    print()
    await test_c_extraction()
    print()
    await test_javascript_extraction()

async def test_java_extraction():
    """Java 함수 추출 테스트"""
    print("☕ Java 함수 추출 테스트")
    print("-" * 50)
    
    java_content = '''package com.example.service;

import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.stream.Collectors;

/**
 * 복잡한 Java 서비스 클래스
 */
public class ComplexJavaService {
    
    private static final String CONSTANT_VALUE = "test";
    private final Map<String, Object> cache = new HashMap<>();
    
    @Autowired
    private DatabaseService databaseService;
    
    /**
     * 기본 생성자
     */
    public ComplexJavaService() {
        this.cache.put("initialized", true);
    }
    
    @Override
    @Deprecated
    public String toString() {
        return "ComplexJavaService{cache=" + cache + "}";
    }
    
    @Async
    @Transactional
    public CompletableFuture<List<String>> processDataAsync(
            List<String> inputData, 
            Map<String, Object> options
    ) {
        return CompletableFuture.supplyAsync(() -> {
            return inputData.stream()
                .filter(Objects::nonNull)
                .map(String::toUpperCase)
                .collect(Collectors.toList());
        });
    }
    
    @GetMapping("/api/data/{id}")
    @ResponseBody
    public ResponseEntity<DataResponse> getData(
            @PathVariable Long id,
            @RequestParam(defaultValue = "10") int limit
    ) {
        try {
            List<String> data = databaseService.findById(id);
            return ResponseEntity.ok(new DataResponse(data));
        } catch (Exception e) {
            return ResponseEntity.status(500).build();
        }
    }
    
    // 제네릭 메서드
    public <T extends Comparable<T>> Optional<T> findMaximum(List<T> items) {
        return items.stream().max(Comparable::compareTo);
    }
    
    // 정적 메서드
    public static void utilityMethod() {
        System.out.println("Utility method called");
    }
    
    // 중첩 클래스
    public static class DataResponse {
        private final List<String> data;
        
        public DataResponse(List<String> data) {
            this.data = data;
        }
        
        public List<String> getData() {
            return data;
        }
    }
}

// 인터페이스
interface ServiceInterface {
    void performAction();
    
    default void defaultMethod() {
        System.out.println("Default implementation");
    }
}'''
    
    functions = await extract_functions_by_type(java_content, 'ComplexJavaService.java', {})
    
    print(f"📊 Java 추출 결과: {len(functions)}개 함수")
    
    # 상세 분석
    java_stats = analyze_extraction_results(functions, ['class', 'method', 'function', 'constructor'])
    
    print(f"  🏛️ 클래스: {java_stats['classes']}개")
    print(f"  🔧 메서드: {java_stats['methods']}개")
    print(f"  📝 함수: {java_stats['functions']}개")
    print(f"  🌐 전역: {java_stats['globals']}개")
    
    # 흥미로운 케이스들
    interesting_cases = find_interesting_java_cases(functions)
    if interesting_cases:
        print(f"  🎯 흥미로운 케이스들:")
        for case in interesting_cases[:3]:
            print(f"    - {case['name']} ({case['reason']})")

async def test_cpp_extraction():
    """C++ 함수 추출 테스트"""
    print("🔧 C++ 함수 추출 테스트")
    print("-" * 50)
    
    cpp_content = '''#include <iostream>
#include <vector>
#include <memory>
#include <algorithm>
#include <functional>

#define MAX_SIZE 1000
#define DEBUG(x) std::cout << "DEBUG: " << x << std::endl

namespace complex {
    
    // 전역 변수
    static int global_counter = 0;
    
    // 함수 템플릿
    template<typename T, typename Predicate>
    std::vector<T> filter(const std::vector<T>& input, Predicate pred) {
        std::vector<T> result;
        std::copy_if(input.begin(), input.end(), 
                     std::back_inserter(result), pred);
        return result;
    }
    
    // 클래스 템플릿
    template<typename T>
    class ComplexContainer {
    private:
        std::vector<T> data_;
        std::unique_ptr<T> special_item_;
        
    public:
        // 생성자
        explicit ComplexContainer(size_t initial_size = 0) 
            : data_(initial_size), special_item_(nullptr) {
            global_counter++;
        }
        
        // 복사 생성자
        ComplexContainer(const ComplexContainer& other) 
            : data_(other.data_), 
              special_item_(other.special_item_ ? 
                  std::make_unique<T>(*other.special_item_) : nullptr) {
        }
        
        // 이동 생성자
        ComplexContainer(ComplexContainer&& other) noexcept 
            : data_(std::move(other.data_)), 
              special_item_(std::move(other.special_item_)) {
        }
        
        // 소멸자
        virtual ~ComplexContainer() {
            global_counter--;
        }
        
        // 연산자 오버로딩
        ComplexContainer& operator=(const ComplexContainer& other) {
            if (this != &other) {
                data_ = other.data_;
                special_item_ = other.special_item_ ? 
                    std::make_unique<T>(*other.special_item_) : nullptr;
            }
            return *this;
        }
        
        // 템플릿 메서드
        template<typename Func>
        void transform(Func func) {
            std::transform(data_.begin(), data_.end(), data_.begin(), func);
        }
        
        // const 메서드
        size_t size() const noexcept {
            return data_.size();
        }
        
        // 가상 함수
        virtual void process() {
            for (auto& item : data_) {
                // 복잡한 처리 로직
                if (special_item_) {
                    item = *special_item_;
                }
            }
        }
    };
    
    // 전역 함수
    void initialize_system() {
        DEBUG("System initialized");
        global_counter = 0;
    }
    
    // 람다를 사용하는 함수
    auto create_processor() -> std::function<void(int&)> {
        return [](int& value) {
            value *= 2;
            if (value > MAX_SIZE) {
                value = MAX_SIZE;
            }
        };
    }
    
} // namespace complex

// 전역 함수 (namespace 외부)
int main(int argc, char* argv[]) {
    try {
        complex::initialize_system();
        
        complex::ComplexContainer<int> container(10);
        container.transform([](int x) { return x * 2; });
        
        auto processor = complex::create_processor();
        // ... more code
        
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }
}'''
    
    functions = await extract_functions_by_type(cpp_content, 'complex_system.cpp', {})
    
    print(f"📊 C++ 추출 결과: {len(functions)}개 함수")
    
    # 상세 분석
    cpp_stats = analyze_extraction_results(functions, ['class', 'method', 'function', 'template'])
    
    print(f"  🏛️ 클래스: {cpp_stats['classes']}개")
    print(f"  🔧 함수: {cpp_stats['functions']}개")
    print(f"  📝 메서드: {cpp_stats['methods']}개")
    print(f"  🌐 전역: {cpp_stats['globals']}개")
    
    # 흥미로운 케이스들
    interesting_cases = find_interesting_cpp_cases(functions)
    if interesting_cases:
        print(f"  🎯 흥미로운 케이스들:")
        for case in interesting_cases[:3]:
            print(f"    - {case['name']} ({case['reason']})")

async def test_c_extraction():
    """C 함수 추출 테스트"""
    print("🔩 C 함수 추출 테스트")
    print("-" * 50)
    
    c_content = '''#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>

#define BUFFER_SIZE 1024
#define MAX_ITEMS 100

// 전역 변수
static int global_count = 0;
static char global_buffer[BUFFER_SIZE];

// 구조체 정의
typedef struct {
    int id;
    char name[50];
    double value;
} DataItem;

typedef struct Node {
    DataItem data;
    struct Node* next;
} Node;

// 함수 포인터 타입 정의
typedef int (*CompareFunc)(const void* a, const void* b);
typedef void (*ProcessFunc)(DataItem* item);

// 전방 선언
void process_data(DataItem* items, int count, ProcessFunc processor);
Node* create_node(DataItem data);

// 메모리 관리 함수들
void* safe_malloc(size_t size) {
    void* ptr = malloc(size);
    if (!ptr) {
        fprintf(stderr, "Memory allocation failed\\n");
        exit(EXIT_FAILURE);
    }
    return ptr;
}

void safe_free(void** ptr) {
    if (ptr && *ptr) {
        free(*ptr);
        *ptr = NULL;
    }
}

// 문자열 처리 함수
char* duplicate_string(const char* source) {
    if (!source) return NULL;
    
    size_t len = strlen(source);
    char* result = (char*)safe_malloc(len + 1);
    strcpy(result, source);
    return result;
}

// 비교 함수들
int compare_by_id(const void* a, const void* b) {
    const DataItem* item_a = (const DataItem*)a;
    const DataItem* item_b = (const DataItem*)b;
    return item_a->id - item_b->id;
}

int compare_by_value(const void* a, const void* b) {
    const DataItem* item_a = (const DataItem*)a;
    const DataItem* item_b = (const DataItem*)b;
    if (item_a->value < item_b->value) return -1;
    if (item_a->value > item_b->value) return 1;
    return 0;
}

// 링크드 리스트 함수들
Node* create_node(DataItem data) {
    Node* node = (Node*)safe_malloc(sizeof(Node));
    node->data = data;
    node->next = NULL;
    global_count++;
    return node;
}

void insert_node(Node** head, DataItem data) {
    Node* new_node = create_node(data);
    if (!*head) {
        *head = new_node;
        return;
    }
    
    // 정렬된 삽입
    if (compare_by_id(&data, &(*head)->data) < 0) {
        new_node->next = *head;
        *head = new_node;
        return;
    }
    
    Node* current = *head;
    while (current->next && 
           compare_by_id(&data, &current->next->data) > 0) {
        current = current->next;
    }
    
    new_node->next = current->next;
    current->next = new_node;
}

void free_list(Node** head) {
    while (*head) {
        Node* temp = *head;
        *head = (*head)->next;
        safe_free((void**)&temp);
        global_count--;
    }
}

// 데이터 처리 함수
void process_data(DataItem* items, int count, ProcessFunc processor) {
    if (!items || !processor) return;
    
    for (int i = 0; i < count; i++) {
        processor(&items[i]);
    }
}

// 파일 I/O 함수
bool save_to_file(const char* filename, DataItem* items, int count) {
    FILE* file = fopen(filename, "wb");
    if (!file) {
        perror("Failed to open file");
        return false;
    }
    
    size_t written = fwrite(items, sizeof(DataItem), count, file);
    fclose(file);
    
    return written == (size_t)count;
}

bool load_from_file(const char* filename, DataItem** items, int* count) {
    FILE* file = fopen(filename, "rb");
    if (!file) {
        perror("Failed to open file");
        return false;
    }
    
    fseek(file, 0, SEEK_END);
    long file_size = ftell(file);
    rewind(file);
    
    *count = file_size / sizeof(DataItem);
    *items = (DataItem*)safe_malloc(file_size);
    
    size_t read = fread(*items, sizeof(DataItem), *count, file);
    fclose(file);
    
    return read == (size_t)*count;
}

// 메인 함수
int main(int argc, char* argv[]) {
    printf("C 함수 추출 테스트 프로그램\\n");
    
    // 테스트 데이터 생성
    DataItem items[] = {
        {1, "First", 10.5},
        {3, "Third", 30.7},
        {2, "Second", 20.3}
    };
    
    int count = sizeof(items) / sizeof(items[0]);
    
    // 정렬
    qsort(items, count, sizeof(DataItem), compare_by_id);
    
    // 파일 저장
    if (save_to_file("data.bin", items, count)) {
        printf("데이터가 성공적으로 저장되었습니다.\\n");
    }
    
    return 0;
}'''
    
    functions = await extract_functions_by_type(c_content, 'data_processor.c', {})
    
    print(f"📊 C 추출 결과: {len(functions)}개 함수")
    
    # 상세 분석
    c_stats = analyze_extraction_results(functions, ['function', 'struct'])
    
    print(f"  🔧 함수: {c_stats['functions']}개")
    print(f"  📦 구조체: {c_stats['classes']}개")  # C에서는 struct가 class 역할
    print(f"  🌐 전역: {c_stats['globals']}개")
    
    # 흥미로운 케이스들
    interesting_cases = find_interesting_c_cases(functions)
    if interesting_cases:
        print(f"  🎯 흥미로운 케이스들:")
        for case in interesting_cases[:3]:
            print(f"    - {case['name']} ({case['reason']})")

async def test_javascript_extraction():
    """JavaScript/TypeScript 함수 추출 테스트"""
    print("🟨 JavaScript 함수 추출 테스트")
    print("-" * 50)
    
    js_content = '''// 복잡한 JavaScript/TypeScript 예제
import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

// 전역 상수
const API_BASE_URL = 'https://api.example.com';
const MAX_RETRIES = 3;

// 타입 정의 (TypeScript)
interface User {
    id: number;
    name: string;
    email: string;
}

interface ApiResponse<T> {
    data: T;
    status: number;
    message: string;
}

// 클래스 정의
class DataManager {
    private cache: Map<string, any> = new Map();
    
    constructor(private baseUrl: string) {
        this.baseUrl = baseUrl;
    }
    
    // 비동기 메서드
    async fetchData<T>(endpoint: string): Promise<ApiResponse<T>> {
        const cacheKey = `${this.baseUrl}${endpoint}`;
        
        if (this.cache.has(cacheKey)) {
            return this.cache.get(cacheKey);
        }
        
        try {
            const response = await axios.get(`${this.baseUrl}${endpoint}`);
            this.cache.set(cacheKey, response.data);
            return response.data;
        } catch (error) {
            console.error('Fetch failed:', error);
            throw new Error(`Failed to fetch ${endpoint}`);
        }
    }
    
    // 제네릭 메서드
    processData<T, R>(data: T[], processor: (item: T) => R): R[] {
        return data.map(processor);
    }
    
    // 정적 메서드
    static validateEmail(email: string): boolean {
        const regex = /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/;
        return regex.test(email);
    }
}

// 화살표 함수들
const createUser = async (userData: Partial<User>): Promise<User> => {
    const response = await fetch(`${API_BASE_URL}/users`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(userData)
    });
    
    if (!response.ok) {
        throw new Error('Failed to create user');
    }
    
    return response.json();
};

const debounce = <T extends (...args: any[]) => any>(
    func: T,
    delay: number
): ((...args: Parameters<T>) => void) => {
    let timeoutId: NodeJS.Timeout;
    
    return (...args: Parameters<T>) => {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => func(...args), delay);
    };
};

// React 컴포넌트 (함수형)
const UserProfile: React.FC<{ userId: number }> = ({ userId }) => {
    const [user, setUser] = useState<User | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    
    const dataManager = new DataManager(API_BASE_URL);
    
    const fetchUser = useCallback(async () => {
        try {
            setLoading(true);
            const response = await dataManager.fetchData<User>(`/users/${userId}`);
            setUser(response.data);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unknown error');
        } finally {
            setLoading(false);
        }
    }, [userId]);
    
    useEffect(() => {
        fetchUser();
    }, [fetchUser]);
    
    const handleEmailChange = debounce((email: string) => {
        if (DataManager.validateEmail(email)) {
            console.log('Valid email:', email);
        }
    }, 300);
    
    if (loading) return <div>Loading...</div>;
    if (error) return <div>Error: {error}</div>;
    if (!user) return <div>User not found</div>;
    
    return (
        <div>
            <h1>{user.name}</h1>
            <p>{user.email}</p>
        </div>
    );
};

// 고차 함수
const withRetry = <T extends (...args: any[]) => Promise<any>>(
    fn: T,
    maxRetries: number = MAX_RETRIES
) => {
    return async (...args: Parameters<T>): Promise<ReturnType<T>> => {
        let lastError: Error;
        
        for (let i = 0; i < maxRetries; i++) {
            try {
                return await fn(...args);
            } catch (error) {
                lastError = error instanceof Error ? error : new Error('Unknown error');
                if (i === maxRetries - 1) break;
                await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)));
            }
        }
        
        throw lastError!;
    };
};

// 전역 함수
function initializeApp() {
    console.log('Application initialized');
    
    // 이벤트 리스너들
    document.addEventListener('DOMContentLoaded', () => {
        console.log('DOM loaded');
    });
    
    window.addEventListener('beforeunload', () => {
        console.log('App is closing');
    });
}

// 즉시 실행 함수
(function() {
    console.log('IIFE executed');
})();

export { DataManager, createUser, UserProfile, withRetry, initializeApp };'''
    
    functions = await extract_functions_by_type(js_content, 'complex_app.ts', {})
    
    print(f"📊 JavaScript 추출 결과: {len(functions)}개 함수")
    
    # 상세 분석
    js_stats = analyze_extraction_results(functions, ['class', 'method', 'function', 'arrow_function'])
    
    print(f"  🏛️ 클래스: {js_stats['classes']}개")
    print(f"  🔧 함수: {js_stats['functions']}개")
    print(f"  📝 메서드: {js_stats['methods']}개")
    print(f"  🌐 전역: {js_stats['globals']}개")
    
    # 흥미로운 케이스들
    interesting_cases = find_interesting_js_cases(functions)
    if interesting_cases:
        print(f"  🎯 흥미로운 케이스들:")
        for case in interesting_cases[:3]:
            print(f"    - {case['name']} ({case['reason']})")

def analyze_extraction_results(functions, expected_types):
    """추출 결과 분석"""
    stats = {
        'total': len(functions),
        'classes': 0,
        'functions': 0,
        'methods': 0,
        'globals': 0,
        'other': 0
    }
    
    for func in functions:
        func_type = func.get('type', 'unknown')
        if func_type in ['class', 'class_header']:
            stats['classes'] += 1
        elif func_type == 'function':
            stats['functions'] += 1
        elif func_type == 'method':
            stats['methods'] += 1
        elif func_type == 'global':
            stats['globals'] += 1
        else:
            stats['other'] += 1
    
    return stats

def find_interesting_java_cases(functions):
    """Java의 흥미로운 케이스들 찾기"""
    interesting = []
    
    for func in functions:
        name = func.get('name', '')
        code = func.get('code', '')
        reasons = []
        
        if '@' in code and code.count('@') > 1:
            reasons.append('다중 어노테이션')
        if 'CompletableFuture' in code:
            reasons.append('비동기 처리')
        if '<' in name and '>' in name:
            reasons.append('제네릭')
        if 'stream()' in code:
            reasons.append('스트림 API')
        if 'lambda' in code or '->' in code:
            reasons.append('람다 표현식')
        
        if reasons:
            interesting.append({
                'name': name,
                'reason': ', '.join(reasons)
            })
    
    return sorted(interesting, key=lambda x: len(x['reason']), reverse=True)

def find_interesting_cpp_cases(functions):
    """C++의 흥미로운 케이스들 찾기"""
    interesting = []
    
    for func in functions:
        name = func.get('name', '')
        code = func.get('code', '')
        reasons = []
        
        if 'template<' in code:
            reasons.append('템플릿')
        if 'std::' in code:
            reasons.append('STL 사용')
        if 'virtual' in code:
            reasons.append('가상 함수')
        if 'operator' in name:
            reasons.append('연산자 오버로딩')
        if 'auto' in code and '->' in code:
            reasons.append('후행 반환 타입')
        if 'noexcept' in code:
            reasons.append('예외 명세')
        
        if reasons:
            interesting.append({
                'name': name,
                'reason': ', '.join(reasons)
            })
    
    return sorted(interesting, key=lambda x: len(x['reason']), reverse=True)

def find_interesting_c_cases(functions):
    """C의 흥미로운 케이스들 찾기"""
    interesting = []
    
    for func in functions:
        name = func.get('name', '')
        code = func.get('code', '')
        reasons = []
        
        if 'typedef' in code:
            reasons.append('타입 정의')
        if '**' in code:
            reasons.append('더블 포인터')
        if 'struct' in code:
            reasons.append('구조체')
        if 'malloc' in code or 'free' in code:
            reasons.append('메모리 관리')
        if 'FILE*' in code:
            reasons.append('파일 I/O')
        if name.startswith('compare_'):
            reasons.append('비교 함수')
        
        if reasons:
            interesting.append({
                'name': name,
                'reason': ', '.join(reasons)
            })
    
    return sorted(interesting, key=lambda x: len(x['reason']), reverse=True)

def find_interesting_js_cases(functions):
    """JavaScript의 흥미로운 케이스들 찾기"""
    interesting = []
    
    for func in functions:
        name = func.get('name', '')
        code = func.get('code', '')
        reasons = []
        
        if '=>' in code:
            reasons.append('화살표 함수')
        if 'async' in code and 'await' in code:
            reasons.append('비동기 함수')
        if '<T' in code or '<T,' in code:
            reasons.append('제네릭 타입')
        if 'useState' in code or 'useEffect' in code:
            reasons.append('React Hooks')
        if 'interface' in code:
            reasons.append('타입스크립트 인터페이스')
        if 'Promise<' in code:
            reasons.append('프로미스 타입')
        
        if reasons:
            interesting.append({
                'name': name,
                'reason': ', '.join(reasons)
            })
    
    return sorted(interesting, key=lambda x: len(x['reason']), reverse=True)

if __name__ == "__main__":
    asyncio.run(test_multi_language_support()) 