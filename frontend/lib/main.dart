import 'package:flutter/material.dart';
import 'package:blue_sphere/presentation/screens/classes_screen.dart';
import 'package:blue_sphere/presentation/screens/load_screen.dart';
import 'package:blue_sphere/presentation/screens/surveys_screen.dart';
import 'package:blue_sphere/presentation/uikit/bottom_nav_bar.dart';
import 'package:blue_sphere/presentation/uikit/colors.dart';
import 'package:vize/vize.dart';
import 'package:flutter_max_miniapp/flutter_max_miniapp.dart';
import 'package:blue_sphere/data/api_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  List<String> userRoles = [];
  List<String> userClassIds = [];

  try {
    final webApp = MaxWebApp();
    webApp.init();

    try {
      await webApp.enableVerticalSwipes();
    } catch (e) {
      print('Свайпы не поддерживаются: $e');
    }

    final initData = webApp.initData;

    if (initData != null && initData.isNotEmpty) {
      // В MAX
      final authData = await ApiService.auth(initData);
      if (authData != null) {
        userRoles = List<String>.from(authData['roles'] ?? []);
        userClassIds = List<String>.from(authData['class_ids'] ?? []);
      }
    } else {
      print('ЛОКАЛЬНЫЙ ВХОД');
      userRoles = ['admin'];
      userClassIds = [];


      ApiService.setTestToken('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMyIsImlhdCI6MTc5MzYwOTMzMiwiZXhwIjoxNzkzNjEyOTMyLCJpc3MiOiJibHVlLXNwaGVyZS1hcGkifQ.vrsMdci53K_f6g3cZ8a51uH9_dfJwQyRh_fA8wkh3dg');
    }
    ApiService.setTestSchoolId(1);


  } catch (e) {
    print('Ошибка инициализации: $e');
  }

  runApp(MyApp(roles: userRoles, classIds: userClassIds));
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
  final List<String> roles;
  final List<String> classIds;

  const MyApp({super.key, required this.roles, required this.classIds});

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
      home: MainScreen(roles: roles, classIds: classIds),
    );
  }
}

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
        onGenerateRoute: (settings) => MaterialPageRoute(
          builder: (context) => LoadScreen(classId: _selectedClassId, className: _selectedClassName, onGoToClasses: () => setState(() => _currentIndex = 0), onGoToSummary: () => setState(() => _currentIndex = isTeacher ? 2 : 1)),
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
          setState(() {
            _currentIndex = index;
          });
        },
      ),
    );
  }
}
