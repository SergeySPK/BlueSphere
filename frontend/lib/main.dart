import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import 'package:flutter_max_miniapp/flutter_max_miniapp.dart';
import 'uikit/colors.dart';
import 'uikit/bottom_nav_bar.dart';
import 'screens/classes_screen.dart';
import 'screens/load_screen.dart';
import 'screens/surveys_screen.dart';
import 'screens/settings_screen.dart';

// Точка входа в приложение

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Инициализация либы flutter_max_miniapp
  try {
    final webApp = MaxWebApp();
    webApp.init();
    await webApp.enableVerticalSwipes();
  } catch (e) {
    print('Ошибка инициализации: $e');
  }

  runApp(const MyApp());
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
        // Инициализация либы Vize
        Vize.init(context, figmaWidth: 375, figmaHeight: 812);
        return child!;
      },
      home: Builder(
        builder: (context) {
          return Container(
            color: white,
            child: Center(
              child: ConstrainedBox(constraints: BoxConstraints(maxWidth: 375), child: MainScreen()),
            ),
          );
        },
      ),
    );
  }
}

class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  int _currentIndex = 0;
  String _selectedClassName = 'Выберите класс';

  @override
  Widget build(BuildContext context) {
    final List<Widget> screens = [
      ClassesScreen(
        onClassSelected: (className) {
          setState(() {
            _selectedClassName = className;
            _currentIndex = 1;
          });
        },
      ),
      LoadScreen(
        className: _selectedClassName,
        onGoToClasses: () {
          setState(() {
            _currentIndex = 0;
          });
        },
      ),
      SurveysScreen(),
      SettingsScreen(),
    ];

    return Scaffold(
      body: IndexedStack(index: _currentIndex, children: screens),
      bottomNavigationBar: BottomNavBar(
        currentIndex: _currentIndex,
        onTap: (index) {
          setState(() {
            _currentIndex = index;
          });
        },
      ),
    );
  }
}
