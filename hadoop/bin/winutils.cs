using System;
class WinUtilsShim {
    static int Main(string[] args) {
        if (args.Length > 0 && args[0] == "systeminfo") {
            Console.WriteLine("vmem:17179869184,pmem:17179869184,vcore:8");
        }
        return 0;
    }
}
