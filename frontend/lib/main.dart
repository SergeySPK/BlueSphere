import 'package:flutter/material.dart';
import 'package:blue_sphere/presentation/screens/classes_screen.dart';
import 'package:blue_sphere/presentation/screens/load_screen.dart';
import 'package:blue_sphere/presentation/screens/surveys_screen.dart';
import 'package:blue_sphere/presentation/screens/splash_screen.dart';
import 'package:blue_sphere/presentation/uikit/bottom_nav_bar.dart';
import 'package:blue_sphere/presentation/uikit/colors.dart';
import 'package:vize/vize.dart';
import 'package:blue_sphere/data/api_service.dart';
import 'package:flutter_max_miniapp/flutter_max_miniapp.dart';

// Точка входа в приложение
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const MyApp());
}

// Функция для перевода ID класса в красивое название
String getRussianClassName(String classId) {
  if (classId.isEmpty) return 'Мой класс';
  final match = RegExp(r'^(\d+)([a-zA-Z]+)$').firstMatch(classId);
  if (match != null) {
    final grade = match.group(1);
    final letter = match.group(2)!.toLowerCase();
    const letters = {
      'a': 'А',
      'b': 'Б',
      'v': 'В',
      'g': 'Г',
      'd': 'Д',
      'e': 'Е',
      'zh': 'Ж',
      'z': 'З',
      'i': 'И',
      'k': 'К',
      'l': 'Л',
      'm': 'М',
      'n': 'Н',
      'o': 'О',
      'p': 'П',
      'r': 'Р',
      's': 'С',
      't': 'Т',
      'u': 'У',
      'f': 'Ф',
      'h': 'Х',
      'c': 'Ц',
      'ch': 'Ч',
      'sh': 'Ш',
      'sch': 'Щ',
      'y': 'Ы',
      'yu': 'Ю',
      'ya': 'Я',
    };
    return '$grade${letters[letter] ?? letter.toUpperCase()}';
  }
  return classId;
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Blue Sphere',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(scaffoldBackgroundColor: background),
      builder: (context, child) {
        Vize.init(context, figmaWidth: 375, figmaHeight: 812);
        return child!;
      },
      home: const AuthWrapper(),
    );
  }
}

class AuthWrapper extends StatefulWidget {
  const AuthWrapper({super.key});

  @override
  State<AuthWrapper> createState() => _AuthWrapperState();
}

class _AuthWrapperState extends State<AuthWrapper> {
  bool _isLoading = true;
  List<String> _roles = [];
  List<String> _classIds = [];

  @override
  void initState() {
    super.initState();
    _initializeApp();
  }

  Future<void> _initializeApp() async {
    try {
      // Инициализируем MAX
      final webApp = MaxWebApp();
      webApp.init();
      try {
        await webApp.enableVerticalSwipes();
      } catch (e) {
        debugPrint('Свайпы недоступны: $e');
      }
      // Получаем данные авторизации
      final initData = webApp.initData;
      if (initData != null && initData.isNotEmpty) {
        // Отправляем данные на бэкенд
        final authData = await ApiService.auth(initData);

        if (authData != null) {
          _roles = List<String>.from(authData['roles'] ?? []);
          _classIds = List<String>.from(authData['class_ids'] ?? []);
        }
      } else {
        debugPrint('initData пуст. Приложение запущено вне MAX.');
      }
    } catch (e) {
      debugPrint('Ошибка инициализации MAX: $e');
    }
    if (mounted) {
      setState(() {
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const SplashScreen();
    }
    // Передаем полученные роли и классы
    return MainScreen(roles: _roles, classIds: _classIds);
  }
}

// Главный экран с вкладками
class MainScreen extends StatefulWidget {
  final List<String> roles;
  final List<String> classIds;

  const MainScreen({super.key, required this.roles, required this.classIds});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  int _currentIndex = 0;
  String _selectedClassId = 'Выберите класс';
  String _selectedClassName = 'Выберите класс';
  final GlobalKey<NavigatorState> _loadNavigatorKey = GlobalKey<NavigatorState>();

  bool get isTeacher => widget.roles.contains('teacher') || widget.roles.contains('admin');

  @override
  void initState() {
    super.initState();
    if (!isTeacher && widget.classIds.isNotEmpty) {
      _selectedClassId = widget.classIds.first;
      _selectedClassName = getRussianClassName(widget.classIds.first);
    }
  }

  @override
  Widget build(BuildContext context) {
    final List<Widget> screens = [];

    if (isTeacher) {
      screens.add(
        ClassesScreen(
          onClassSelected: (id, name) {
            setState(() {
              _selectedClassId = id;
              _selectedClassName = name;
              _currentIndex = 1;
            });
          },
        ),
      );
    }

    screens.add(
      Navigator(
        key: _loadNavigatorKey,
        onGenerateRoute: (settings) => MaterialPageRoute(
          builder: (context) =>
              LoadScreen(classId: _selectedClassId, className: _selectedClassName, isTeacher: isTeacher, onGoToClasses: () => setState(() => _currentIndex = 0), onGoToSummary: () => setState(() => _currentIndex = isTeacher ? 2 : 1)),
        ),
      ),
    );

    screens.add(SurveysScreen(classId: _selectedClassId, className: _selectedClassName, onGoToClasses: () => setState(() => _currentIndex = 0)));

    return Scaffold(
      backgroundColor: background,
      body: IndexedStack(index: _currentIndex, children: screens),
      bottomNavigationBar: BottomNavBar(
        currentIndex: _currentIndex,
        isTeacher: isTeacher,
        onTap: (index) {
          if (index == (isTeacher ? 1 : 0)) {
            _loadNavigatorKey.currentState?.popUntil((route) => route.isFirst);
          }
          setState(() {
            _currentIndex = index;
          });
        },
      ),
    );
  }
}
