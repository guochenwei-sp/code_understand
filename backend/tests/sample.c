#include <stdio.h>

#define MAX_BUFFER 1024

// 一个简单的结构体
typedef struct Point {
    int x;
    int y;
} Point_t;

// 全局变量
int g_counter = 0;

/**
 * 计算两点之和
 */
Point_t add_points(Point_t a, Point_t b) {
    Point_t result;
    result.x = a.x + b.x;
    result.y = a.y + b.y;
    return result;
}

// 主函数
int main() {
    Point_t p1 = {1, 2};
    Point_t p2 = {3, 4};
    
    Point_t p3 = add_points(p1, p2);
    
    printf("Result: %d, %d\n", p3.x, p3.y);
    return 0;
}

