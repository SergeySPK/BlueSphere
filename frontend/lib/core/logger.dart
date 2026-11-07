import 'dart:developer' as developer;

// Утилита для логирования запросов и ошибок в консоль
class AppLogger {
  static void info(String message, {String tag = 'APP'}) {
    developer.log(message, name: tag, level: 800);
  }

  static void error(String message, {Object? error, StackTrace? stackTrace, String tag = 'APP'}) {
    developer.log(message, name: tag, level: 1000, error: error, stackTrace: stackTrace);
  }
}
