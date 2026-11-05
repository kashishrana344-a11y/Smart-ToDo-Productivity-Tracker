from .app import ProductivityApp

def main():
    try:
        app = ProductivityApp()
        app.mainloop()
    except Exception as exc:
        import tkinter.messagebox as mb
        mb.showerror("Flowday could not start", f"{exc}\n\nCheck that Python and Tkinter are installed.")
        raise

if __name__ == "__main__": main()
