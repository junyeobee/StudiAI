import asyncio
import logging
import sys
from pathlib import Path

# 프로젝트 루트 디렉터리를 Python 경로에 추가
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent  # tests/debug/ -> tests/ -> 루트
sys.path.insert(0, str(project_root))

from app.services.extract_for_file_service import extract_functions_by_type

# 디버그 로깅 활성화
logging.getLogger('api').setLevel(logging.DEBUG)

async def debug_language_parsing():
    """언어별 파싱 결과 상세 디버깅"""
    
    print("🔍 언어별 파싱 결과 상세 디버깅")
    print("=" * 80)
    
    # 각 언어별 간단한 테스트부터
    await debug_simple_java()
    print()
    await debug_simple_cpp()
    print()
    await debug_simple_c()
    print()

async def debug_simple_java():
    """간단한 Java 코드 디버깅"""
    print("☕ 간단한 Java 코드 디버깅")
    print("-" * 50)
    
    simple_java = '''public class SimpleClass {
    
    private int value;
    
    public SimpleClass() {
        this.value = 0;
    }
    
    @Override
    public String toString() {
        return "SimpleClass{value=" + value + "}";
    }
    
    public void setValue(int value) {
        this.value = value;
    }
    
    public int getValue() {
        return value;
    }
}'''
    
    functions = await extract_functions_by_type(simple_java, 'SimpleClass.java', {})
    
    print(f"📊 Java 추출 결과: {len(functions)}개")
    for i, func in enumerate(functions, 1):
        name = func['name']
        func_type = func['type']
        start_line = func['start_line']
        end_line = func['end_line']
        code_length = len(func['code'])
        
        print(f"  {i:2d}. {name:20} | {func_type:10} | {start_line:2d}-{end_line:2d} | {code_length:3d}자")
        
        # 흥미로운 케이스들 (처음 2개)
        if i <= 2:
            print(f"      📝 코드 미리보기:")
            code_lines = func['code'].split('\n')[:3]
            for j, line in enumerate(code_lines, 1):
                print(f"        {j}: {repr(line[:50])}")

async def debug_simple_cpp():
    """간단한 C++ 코드 디버깅"""
    print("🔧 간단한 C++ 코드 디버깅")
    print("-" * 50)
    
    simple_cpp = '''#include <iostream>

class SimpleClass {
private:
    int value_;
    
public:
    SimpleClass() : value_(0) {
        std::cout << "Constructor called" << std::endl;
    }
    
    ~SimpleClass() {
        std::cout << "Destructor called" << std::endl;
    }
    
    void setValue(int value) {
        value_ = value;
    }
    
    int getValue() const {
        return value_;
    }
};

void globalFunction() {
    std::cout << "Global function called" << std::endl;
}

int main() {
    SimpleClass obj;
    obj.setValue(42);
    globalFunction();
    return 0;
}'''
    
    functions = await extract_functions_by_type(simple_cpp, 'SimpleClass.cpp', {})
    
    print(f"📊 C++ 추출 결과: {len(functions)}개")
    for i, func in enumerate(functions, 1):
        name = func['name']
        func_type = func['type']
        start_line = func['start_line']
        end_line = func['end_line']
        code_length = len(func['code'])
        
        print(f"  {i:2d}. {name:20} | {func_type:10} | {start_line:2d}-{end_line:2d} | {code_length:3d}자")
        
        # 흥미로운 케이스들 (처음 3개)
        if i <= 3:
            print(f"      📝 코드 미리보기:")
            code_lines = func['code'].split('\n')[:3]
            for j, line in enumerate(code_lines, 1):
                print(f"        {j}: {repr(line[:50])}")

async def debug_simple_c():
    """간단한 C 코드 디버깅"""
    print("🔩 간단한 C 코드 디버깅")
    print("-" * 50)
    
    simple_c = '''#include <stdio.h>
#include <stdlib.h>

typedef struct {
    int id;
    char name[50];
} Person;

void print_person(Person* p) {
    printf("Person: id=%d, name=%s\\n", p->id, p->name);
}

Person* create_person(int id, const char* name) {
    Person* p = (Person*)malloc(sizeof(Person));
    p->id = id;
    strncpy(p->name, name, 49);
    p->name[49] = '\\0';
    return p;
}

void free_person(Person* p) {
    if (p) {
        free(p);
    }
}

int main() {
    Person* p = create_person(1, "John");
    print_person(p);
    free_person(p);
    return 0;
}'''
    
    functions = await extract_functions_by_type(simple_c, 'person.c', {})
    
    print(f"📊 C 추출 결과: {len(functions)}개")
    for i, func in enumerate(functions, 1):
        name = func['name']
        func_type = func['type']
        start_line = func['start_line']
        end_line = func['end_line']
        code_length = len(func['code'])
        
        print(f"  {i:2d}. {name:20} | {func_type:10} | {start_line:2d}-{end_line:2d} | {code_length:3d}자")
        
        # 흥미로운 케이스들 (처음 3개)
        if i <= 3:
            print(f"      📝 코드 미리보기:")
            code_lines = func['code'].split('\n')[:3]
            for j, line in enumerate(code_lines, 1):
                print(f"        {j}: {repr(line[:50])}")

if __name__ == "__main__":
    asyncio.run(debug_language_parsing()) 